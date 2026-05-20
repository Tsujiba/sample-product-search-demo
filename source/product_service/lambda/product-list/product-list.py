"""
product-list: 商品一覧取得Lambda
- DynamoDBから商品一覧を取得（ページネーション対応）
"""
import json
import boto3
import os
from decimal import Decimal

DYNAMO_PRODUCT_TABLE = os.environ["DYNAMO_PRODUCT_TABLE"]
S3_DATA_BUCKET = os.environ["S3_DATA_BUCKET"]
S3_PRESIGNED_URL_EXPIRY_S = int(os.environ.get("S3_PRESIGNED_URL_EXPIRY_S", "3600"))

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
product_table = dynamodb.Table(DYNAMO_PRODUCT_TABLE)


class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return int(o) if o == int(o) else float(o)
        return super().default(o)


def lambda_handler(event, context):
    """
    入力:
    {
      "category": "",           # カテゴリフィルタ（任意）
      "limit": 20,
      "last_evaluated_key": {}  # ページネーション用
    }
    """
    category = event.get("category", "")
    limit = event.get("limit", 20)
    last_key = event.get("last_evaluated_key")

    if category:
        params = {
            "IndexName": "category-index",
            "KeyConditionExpression": boto3.dynamodb.conditions.Key("category").eq(category),
            "Limit": limit,
            "ScanIndexForward": False,
        }
        if last_key:
            params["ExclusiveStartKey"] = last_key
        response = product_table.query(**params)
    else:
        params = {"Limit": limit}
        if last_key:
            params["ExclusiveStartKey"] = last_key
        response = product_table.scan(**params)

    items = response.get("Items", [])

    # presigned URL付与
    for item in items:
        if item.get("image_s3_key"):
            item["image_url"] = s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": S3_DATA_BUCKET, "Key": item["image_s3_key"]},
                ExpiresIn=S3_PRESIGNED_URL_EXPIRY_S,
            )
        # text_contentは一覧では先頭100文字のみ
        if item.get("text_content"):
            item["text_content"] = item["text_content"][:100]

    result = {
        "items": json.loads(json.dumps(items, cls=DecimalEncoder)),
        "count": len(items),
    }
    if response.get("LastEvaluatedKey"):
        result["last_evaluated_key"] = json.loads(json.dumps(response["LastEvaluatedKey"], cls=DecimalEncoder))

    return {"statusCode": 200, "body": result}
