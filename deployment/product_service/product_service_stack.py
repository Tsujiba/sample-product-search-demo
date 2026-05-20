from aws_cdk import (
    NestedStack,
    Size,
    aws_s3 as _s3,
    aws_lambda as _lambda,
    aws_apigateway as _apigw,
    aws_iam as _iam,
    aws_dynamodb as _dynamodb,
    Duration,
    RemovalPolicy,
    aws_logs as logs,
    custom_resources,
    CfnOutput,
)
from aws_cdk.aws_apigateway import IdentitySource
from aws_cdk.aws_logs import RetentionDays
from aws_cdk import aws_cognito as _cognito
from constructs import Construct
import os
import json
from product_service.constant import *


class ProductServiceStack(NestedStack):

    api_gw_base_url = None

    def __init__(self, scope: Construct, construct_id: str,
                 cognito_user_pool_id: str,
                 cognito_app_client_id: str,
                 s3_data_bucket_name: str,
                 **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self._acct = os.environ.get("CDK_DEFAULT_ACCOUNT")
        self._rgn = os.environ.get("CDK_DEFAULT_REGION")
        self.s3_data_bucket_name = s3_data_bucket_name
        self.cognito_user_pool_id = cognito_user_pool_id
        self.cognito_app_client_id = cognito_app_client_id

        self.deploy_dynamodb()
        self.deploy_s3_vectors()
        self.deploy_cognito()
        self.deploy_lambda_layers()
        self.deploy_apigw()

    def deploy_dynamodb(self):
        """商品マスタテーブル"""
        self.product_table = _dynamodb.Table(
            self, "ProductMasterTable",
            table_name=DYNAMO_PRODUCT_TABLE,
            partition_key=_dynamodb.Attribute(name="product_id", type=_dynamodb.AttributeType.STRING),
            point_in_time_recovery=True,
            removal_policy=RemovalPolicy.DESTROY,
            billing_mode=_dynamodb.BillingMode.PAY_PER_REQUEST,
        )
        self.product_table.add_global_secondary_index(
            index_name="product_code-index",
            partition_key=_dynamodb.Attribute(name="product_code", type=_dynamodb.AttributeType.STRING),
            projection_type=_dynamodb.ProjectionType.ALL,
        )
        self.product_table.add_global_secondary_index(
            index_name="category-index",
            partition_key=_dynamodb.Attribute(name="category", type=_dynamodb.AttributeType.STRING),
            sort_key=_dynamodb.Attribute(name="created_at", type=_dynamodb.AttributeType.STRING),
            projection_type=_dynamodb.ProjectionType.ALL,
        )

    def deploy_s3_vectors(self):
        """S3 Vectors インデックスをCustomResourceで作成"""
        lambda_key = "product-provision-vectors"
        provision_role = _iam.Role(
            self, "ProductVectorProvisionRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={f"{lambda_key}-policy": _iam.PolicyDocument(
                statements=[
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["s3vectors:*"],
                        resources=[
                            f"arn:aws:s3vectors:{self._rgn}:{self._acct}:bucket/{S3_VECTOR_BUCKET_NAME}",
                            f"arn:aws:s3vectors:{self._rgn}:{self._acct}:bucket/{S3_VECTOR_BUCKET_NAME}/*",
                        ]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
                        resources=[f"arn:aws:logs:{self._rgn}:{self._acct}:*"]
                    ),
                ]
            )}
        )

        provision_lambda = _lambda.Function(
            self, "ProductVectorProvisionLambda",
            function_name=f"{LAMBDA_NAME_PREFIX}product-provision-vectors",
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler="index.on_event",
            code=_lambda.Code.from_inline(self._get_provision_code()),
            timeout=Duration.minutes(5),
            role=provision_role,
            memory_size=256,
        )

        # boto3 layer for s3vectors support
        layer_bucket = _s3.Bucket.from_bucket_name(self, "LayerBucket", bucket_name=self.s3_data_bucket_name)
        boto3_layer = _lambda.LayerVersion(self, "ProductBoto3Layer",
            code=_lambda.S3Code(bucket=layer_bucket, key=LAMBDA_LAYER_SOURCE_S3_KEY_BOTO3),
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_13],
            description="boto3 layer for product service"
        )
        provision_lambda.add_layers(boto3_layer)

        # Invoke provision lambda
        invoke_role = _iam.Role(
            self, "ProductVectorProvisionInvokeRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={"invoke-policy": _iam.PolicyDocument(
                statements=[
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["lambda:InvokeFunction"],
                        resources=[provision_lambda.function_arn]
                    )
                ]
            )}
        )

        custom_resources.AwsCustomResource(
            self, "ProductVectorProvisionInvoke",
            log_retention=RetentionDays.ONE_WEEK,
            on_create=custom_resources.AwsSdkCall(
                service="Lambda",
                action="invoke",
                physical_resource_id=custom_resources.PhysicalResourceId.of("ProductVectorProvision"),
                parameters={
                    "FunctionName": provision_lambda.function_name,
                    "InvocationType": "RequestResponse",
                    "Payload": json.dumps({
                        "RequestType": "Create",
                        "S3Vectors": [
                            {"BucketName": S3_VECTOR_BUCKET_NAME, "IndexName": S3_VECTOR_INDEX_PRODUCT_IMAGE, "IndexDim": EMBEDDING_DIM},
                            {"BucketName": S3_VECTOR_BUCKET_NAME, "IndexName": S3_VECTOR_INDEX_PRODUCT_TEXT, "IndexDim": EMBEDDING_DIM},
                        ]
                    })
                },
                output_paths=["Payload"]
            ),
            role=invoke_role
        )

        self.boto3_layer = boto3_layer

    def _get_provision_code(self):
        return '''
import boto3
import json

def on_event(event, context):
    s3vectors = boto3.client("s3vectors")
    results = []
    for vec_config in event.get("S3Vectors", []):
        bucket_name = vec_config["BucketName"]
        index_name = vec_config["IndexName"]
        dim = int(vec_config["IndexDim"])
        try:
            s3vectors.create_index(
                vectorBucketName=bucket_name,
                indexName=index_name,
                dimension=dim,
                distanceMetric="cosine",
                dataType="float32"
            )
            results.append(f"Created index {index_name}")
        except s3vectors.exceptions.ConflictException:
            results.append(f"Index {index_name} already exists")
        except Exception as e:
            results.append(f"Error creating {index_name}: {str(e)}")
    return {"statusCode": 200, "body": json.dumps(results)}
'''

    def deploy_cognito(self):
        user_pool = _cognito.UserPool.from_user_pool_id(self, "ProductUserPool", user_pool_id=self.cognito_user_pool_id)
        self.cognito_authorizer = _apigw.CognitoUserPoolsAuthorizer(
            self, "ProductWebAuth",
            cognito_user_pools=[user_pool],
            identity_source=IdentitySource.header("Authorization")
        )

    def deploy_lambda_layers(self):
        # boto3_layer is already created in deploy_s3_vectors
        pass

    def deploy_apigw(self):
        """API Gateway + Lambda endpoints"""
        api = _apigw.RestApi(
            self, f"{API_NAME_PREFIX}Api",
            rest_api_name=f"{API_NAME_PREFIX}-api",
            cloud_watch_role=True,
            cloud_watch_role_removal_policy=RemovalPolicy.DESTROY,
            deploy_options=_apigw.StageOptions(
                tracing_enabled=True,
                access_log_destination=_apigw.LogGroupLogDestination(
                    logs.LogGroup(self, "ProductApiAccessLog")
                ),
                access_log_format=_apigw.AccessLogFormat.clf(),
                method_options={
                    "/*/*": _apigw.MethodDeploymentOptions(
                        logging_level=_apigw.MethodLoggingLevel.INFO,
                    )
                },
            ),
        )
        self.api_gw_base_url = api.url

        v1 = api.root.add_resource("v1")
        products = v1.add_resource("products")

        # --- product-register ---
        register_role = self._create_lambda_role("ProductRegister", "product-register", include_bedrock=True, include_s3vectors=True)
        self._create_api_endpoint(
            id="ProductRegisterEp", root=products, path="register", method="POST",
            role=register_role, lambda_file_name="product-register",
            memory_m=1024, timeout_s=900,
            envs={
                "DYNAMO_PRODUCT_TABLE": DYNAMO_PRODUCT_TABLE,
                "S3_DATA_BUCKET": self.s3_data_bucket_name,
                "S3_VECTOR_BUCKET": S3_VECTOR_BUCKET_NAME,
                "S3_VECTOR_INDEX_IMAGE": S3_VECTOR_INDEX_PRODUCT_IMAGE,
                "S3_VECTOR_INDEX_TEXT": S3_VECTOR_INDEX_PRODUCT_TEXT,
                "MODEL_ID": MODEL_ID_BEDROCK_MME,
                "EMBEDDING_DIM": EMBEDDING_DIM,
            }
        )

        # --- product-search ---
        search_role = self._create_lambda_role("ProductSearch", "product-search", include_bedrock=True, include_s3vectors=True)
        self._create_api_endpoint(
            id="ProductSearchEp", root=products, path="search", method="POST",
            role=search_role, lambda_file_name="product-search",
            memory_m=512, timeout_s=30,
            envs={
                "DYNAMO_PRODUCT_TABLE": DYNAMO_PRODUCT_TABLE,
                "S3_DATA_BUCKET": self.s3_data_bucket_name,
                "S3_VECTOR_BUCKET": S3_VECTOR_BUCKET_NAME,
                "S3_VECTOR_INDEX_IMAGE": S3_VECTOR_INDEX_PRODUCT_IMAGE,
                "S3_VECTOR_INDEX_TEXT": S3_VECTOR_INDEX_PRODUCT_TEXT,
                "MODEL_ID": MODEL_ID_BEDROCK_MME,
                "EMBEDDING_DIM": EMBEDDING_DIM,
                "S3_PRESIGNED_URL_EXPIRY_S": S3_PRE_SIGNED_URL_EXPIRY_S,
            }
        )

        # --- product-list ---
        list_role = self._create_lambda_role("ProductList", "product-list", include_bedrock=False, include_s3vectors=False)
        self._create_api_endpoint(
            id="ProductListEp", root=products, path="list", method="POST",
            role=list_role, lambda_file_name="product-list",
            memory_m=256, timeout_s=10,
            envs={
                "DYNAMO_PRODUCT_TABLE": DYNAMO_PRODUCT_TABLE,
                "S3_DATA_BUCKET": self.s3_data_bucket_name,
                "S3_PRESIGNED_URL_EXPIRY_S": S3_PRE_SIGNED_URL_EXPIRY_S,
            }
        )

    def _create_lambda_role(self, name: str, lambda_name: str, include_bedrock: bool, include_s3vectors: bool):
        statements = [
            _iam.PolicyStatement(
                effect=_iam.Effect.ALLOW,
                actions=["logs:CreateLogGroup"],
                resources=[f"arn:aws:logs:{self._rgn}:{self._acct}:*"]
            ),
            _iam.PolicyStatement(
                effect=_iam.Effect.ALLOW,
                actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                resources=[f"arn:aws:logs:{self._rgn}:{self._acct}:log-group:/aws/lambda/{LAMBDA_NAME_PREFIX}{lambda_name}:*"]
            ),
            _iam.PolicyStatement(
                actions=["dynamodb:Query", "dynamodb:Scan", "dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:BatchWriteItem"],
                resources=[
                    f"arn:aws:dynamodb:{self._rgn}:{self._acct}:table/{DYNAMO_PRODUCT_TABLE}",
                    f"arn:aws:dynamodb:{self._rgn}:{self._acct}:table/{DYNAMO_PRODUCT_TABLE}/index/*",
                ]
            ),
            _iam.PolicyStatement(
                effect=_iam.Effect.ALLOW,
                actions=["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
                resources=[
                    f"arn:aws:s3:::{self.s3_data_bucket_name}",
                    f"arn:aws:s3:::{self.s3_data_bucket_name}/*",
                ]
            ),
        ]
        if include_bedrock:
            statements.append(_iam.PolicyStatement(
                effect=_iam.Effect.ALLOW,
                actions=["bedrock:InvokeModel"],
                resources=["arn:aws:bedrock:*:*:foundation-model/*"]
            ))
        if include_s3vectors:
            statements.append(_iam.PolicyStatement(
                effect=_iam.Effect.ALLOW,
                actions=["s3vectors:*"],
                resources=[
                    f"arn:aws:s3vectors:{self._rgn}:{self._acct}:bucket/{S3_VECTOR_BUCKET_NAME}",
                    f"arn:aws:s3vectors:{self._rgn}:{self._acct}:bucket/{S3_VECTOR_BUCKET_NAME}/*",
                ]
            ))

        return _iam.Role(
            self, f"{name}LambdaRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={f"{lambda_name}-policy": _iam.PolicyDocument(statements=statements)}
        )

    def _create_api_endpoint(self, id, root, path, method, role, lambda_file_name, memory_m, timeout_s, envs):
        lambda_function = _lambda.Function(
            self, id,
            function_name=f"{LAMBDA_NAME_PREFIX}{lambda_file_name}",
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler=f"{lambda_file_name}.lambda_handler",
            code=_lambda.Code.from_asset(os.path.join("../source/", f"product_service/lambda/{lambda_file_name}")),
            timeout=Duration.seconds(timeout_s),
            memory_size=memory_m,
            ephemeral_storage_size=Size.mebibytes(512),
            role=role,
            environment=envs,
            layers=[self.boto3_layer],
        )

        resource = root.add_resource(
            path,
            default_cors_preflight_options=_apigw.CorsOptions(
                allow_methods=["POST", "OPTIONS"],
                allow_origins=_apigw.Cors.ALL_ORIGINS,
            ),
        )

        resource.add_method(
            method,
            _apigw.LambdaIntegration(
                lambda_function,
                proxy=False,
                integration_responses=[
                    _apigw.IntegrationResponse(
                        status_code="200",
                        response_parameters={"method.response.header.Access-Control-Allow-Origin": "'*'"}
                    )
                ]
            ),
            method_responses=[
                _apigw.MethodResponse(
                    status_code="200",
                    response_parameters={"method.response.header.Access-Control-Allow-Origin": True}
                )
            ],
            authorizer=self.cognito_authorizer,
            authorization_type=_apigw.AuthorizationType.COGNITO,
        )
