#!/usr/bin/env python3
import aws_cdk as cdk
from aws_cdk import CfnParameter as _cfnParameter
from aws_cdk import Stack,CfnOutput
from aws_cdk import Duration

import os, json
#from nova_service.nova_service_pre_stack import NovaServicePreStack
from nova_service.nova_service_stack import NovaServiceStack
from product_service.product_service_stack import ProductServiceStack
from pre_stack.service_pre_stack import ServicePreStack
from post_stack.service_post_stack import ServicePostStack
from frontend.frontend_stack import FrontendStack
from cdk_nag import AwsSolutionsChecks, NagSuppressions
import secrets
import string
import random

env = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT"), 
    region=os.environ.get("CDK_DEFAULT_REGION")
)

class RootStack(Stack):
    user_emails = None
    user_name = None
    password = None

    def __init__(self, scope):
        super().__init__(scope, id="NovaMmeRootStack", env=env, description="Nova MME stack.",
        )

        # Inputs
        input_user_emails = _cfnParameter(self, "inputUserEmails", type="String",
                                    description="Use your email to log in to the web portal. Split by comma if there are multiple emails.",
                                )
        self.user_emails = input_user_emails.value_as_string
        
        # Preparation stack
        srv_pre_stack = ServicePreStack(self, 
            "NovaMmePreStack", 
            description="Deploy S3 data bucket, Cognito user pool, build Lambda Layers, deploy S3 vector bucket and index.",
            timeout = Duration.hours(1)
        )

        # Nova service stack
        nova_service_stack = NovaServiceStack(self, 
            "NovaMMeServiceStack", 
            description="Deploy Nova backend services: DynamoDB, API Gateway, Lambda, etc.",
            timeout = Duration.hours(4),
            s3_bucket_name_mm = srv_pre_stack.s3_data_bucket_name,
            cognito_user_pool_id=srv_pre_stack.cognito_user_pool_id,
            cognito_app_client_id=srv_pre_stack.cognito_app_client_id
        )
        nova_service_stack.node.add_dependency(srv_pre_stack)

        # Product service stack (商品画像検索)
        product_service_stack = ProductServiceStack(self,
            "ProductServiceStack",
            description="Deploy product search services: DynamoDB, S3 Vectors, API Gateway, Lambda.",
            timeout=Duration.hours(1),
            cognito_user_pool_id=srv_pre_stack.cognito_user_pool_id,
            cognito_app_client_id=srv_pre_stack.cognito_app_client_id,
            s3_data_bucket_name=srv_pre_stack.s3_data_bucket_name,
        )
        product_service_stack.node.add_dependency(srv_pre_stack)

        # Frontend stack
        frontend_stack = FrontendStack(self, 
            "NovaMmeFrontStack", 
            description="Deploy frontend static website: S3, CloudFormation",
            api_gw_base_url_nova_srv = nova_service_stack.api_gw_base_url,
            cognito_user_pool_id = srv_pre_stack.cognito_user_pool_id,
            cognito_app_client_id = srv_pre_stack.cognito_app_client_id,
            cognito_identity_pool_id = srv_pre_stack.cognito_identity_pool_id,
            s3_bucket_name_data = srv_pre_stack.s3_data_bucket_name,
        )
        frontend_stack.node.add_dependency(nova_service_stack)

        # Service post stack
        service_post_stack = ServicePostStack(self, 
            "NovaMmePostStack", 
            description="Create Cognito user, send invitation email",
            s3_web_bucket_name = frontend_stack.s3_web_bucket_name,
            s3_data_bucket_name = srv_pre_stack.s3_data_bucket_name,
            cloudfront_url = frontend_stack.output_url,
            cognito_user_pool_id = srv_pre_stack.cognito_user_pool_id,
            cognito_app_client_id = srv_pre_stack.cognito_app_client_id,
            user_emails = self.user_emails,
        )
        service_post_stack.node.add_dependency(frontend_stack)

        CfnOutput(self, "Website URL", value=f"https://{frontend_stack.output_url}")

        CfnOutput(self, "API Gateway Base URL: Nova MME Service", value=nova_service_stack.api_gw_base_url)

        CfnOutput(self, "API Gateway Base URL: Product Service", value=product_service_stack.api_gw_base_url)

        
        CfnOutput(self, "Cognito User Pool Id", value=srv_pre_stack.cognito_user_pool_id)
        CfnOutput(self, "Cognito App Client Id", value=srv_pre_stack.cognito_app_client_id)
        CfnOutput(self, "Cognito Identity Pool Id", value=srv_pre_stack.cognito_identity_pool_id)


app = cdk.App()
root_stack = RootStack(app)

nag_suppressions = [
        {
            "id": "AwsSolutions-IAM5",
            "reason": "AWS managed policies are allowed which sometimes uses * in the resources like - AWSGlueServiceRole has aws-glue-* . AWS Managed IAM policies have been allowed to maintain secured access with the ease of operational maintenance - however for more granular control the custom IAM policies can be used instead of AWS managed policies",
        },
        {
            "id": "AwsSolutions-IAM4",
            "reason": "AWS Managed IAM policies have been allowed to maintain secured access with the ease of operational maintenance - however for more granular control the custom IAM policies can be used instead of AWS managed policies",
        },
        {
            'id': 'AwsSolutions-APIG2',
            'reason': 'API request validation is handled within the Lambda functions.'
        },
        {
            'id': 'AwsSolutions-APIG4',
            'reason': 'False Positive detection. All API Gateway methods are authorized using a Cognitio authrozier provisioned in the CDK.'
        },
        {
            'id': 'AwsSolutions-COG4',
            'reason': 'False Positive detection. All API Gateway methods are authorized using a Cognitio authrozier provisioned in the CDK.'
        },
        {
            'id': 'AwsSolutions-S1',
            'reason': 'The CloudFront access log bucket has logging disabled. It is up to the user to decide whether to enable the access log to the log bucket.'
        },
        {
            'id': 'AwsSolutions-CFR4',
            'reason': 'The internal admin web portal is deployed using the default CloudFront domain and certification. User can set up DNS to route the web portal through their managed domain and replace the certification to resolve this issue.'
        },
        {
            'id': 'AwsSolutions-COG3',
            'reason': 'The Cognito user pool is used for an admin web UI authentication and does not allow public registration. Enabling AdvancedSecurityMode is optional and left to the users discretion.'
        },
        {
            'id': 'AwsSolutions-CFR7',
            'reason': 'False positive. The CloudFromation distribution has enbaled OAI access to the S3 origin.'
        },
        {
            'id': 'AwsSolutions-L1',
            'reason': 'False positive. There is no Lambda deployment in the analytics stack.'
        },
        {
            'id': 'AwsSolutions-CB4',
            'reason': 'The target s3 bucket is for public web hosting which does not require encryption.'
        },
    ]

NagSuppressions.add_stack_suppressions(
    root_stack,
    nag_suppressions,
    apply_to_nested_stacks=True
)

cdk.Aspects.of(app).add(AwsSolutionsChecks())

app.synth()
