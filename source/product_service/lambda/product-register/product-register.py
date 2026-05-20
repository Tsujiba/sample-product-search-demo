"""
product-register: 商品データ登録Lambda
- S3上のCSV + テキストファイル + 画像ファイルから商品を登録
- Nova Embeddings でベクトル化し S3 Vectors + DynamoDB + OpenSearch に保存
"""
import json
import boto3
import os
import base64
import uuid
import time
import csv
import io

DYNAMO_PRODUCT_TABLE = os.environ["DYNAMO_PRODUCT_TABLE"]
S3_DATA_BUCKET = os.environ["S3_DATA_BUCKET"]
S3_VECTOR_BUCKET = os.environ["S3_VECTOR_BUCKET"]
S3_VECTOR_INDEX_IMAGE = os.environ["S3_VECTOR_INDEX_IMAGE"]
S3_VECTOR_INDEX_TEXT = os.environ["S3_VECTOR_INDEX_TEXT"]
MODEL_ID = os.environ["MODEL_ID"]
EMBEDDING_DIM = int(os.environ.get("EMBEDDING_DIM", "1024"))
AOSS_ENDPOINT = os.environ.get("AOSS_ENDPOINT", "")
AOSS_INDEX_NAME = os.environ.get("AOSS_INDEX_NAME", "product-vectors")

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
bedrock = boto3.client("bedrock-runtime")
s3vectors = boto3.client("s3vectors")

product_table = dynamodb.Table(DYNAMO_PRODUCT_TABLE)

# OpenSearch client (lazy init)
_os_client = None

def get_os_client():
    global _os_client
    if _os_client is None and AOSS_ENDPOINT:
        from opensearchpy import OpenSearch, RequestsHttpConnection
        from requests_aws4auth import AWS4Auth
        credentials = boto3.Session().get_credentials().get_frozen_credentials()
        auth = AWS4Auth(credentials.access_key, credentials.secret_key,
                        os.environ.get("AWS_REGION", "us-east-1"), "aoss",
                        session_token=credentials.token)
        host = AOSS_ENDPOINT.replace("https://", "")
        _os_client = OpenSearch(
            hosts=[{"host": host, "port": 443}],
            http_auth=auth, use_ssl=True, verify_certs=True,
            connection_class=RequestsHttpConnection, timeout=30
        )
    return _os_client


def lambda_handler(event, context):
    """
    入力:
    {
      "s3_prefix": "upload/batch001/",   # S3上のデータフォルダ
      "csv_key": "upload/batch001/products.csv"  # (optional) CSVファイルのキー
    }
    または単品登録:
    {
      "product_code": "A00001",
      "product_name": "もこもこくつした",
      "category": "靴下",
      "price": 1500,
      "text_content": "◆キャッチコピー...",
      "image_base64": "...",
      "image_format": "jpeg"
    }
    """
    # 単品登録
    if event.get("product_code"):
        return register_single(event)

    # バッチ登録（S3上のCSV + ファイル群）
    s3_prefix = event.get("s3_prefix", "")
    csv_key = event.get("csv_key", f"{s3_prefix}products.csv")
    return register_batch(s3_prefix, csv_key)


def register_single(event):
    product_code = event["product_code"]
    product_id = str(uuid.uuid4())
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    text_content = event.get("text_content", "")
    image_base64 = event.get("image_base64", "")
    image_format = event.get("image_format", "jpeg")

    # Embedding生成
    text_embedding = embed_text(text_content) if text_content else None
    image_embedding = embed_image(image_base64, image_format) if image_base64 else None

    # S3に画像保存
    image_s3_key = ""
    if image_base64:
        image_s3_key = f"products/images/{product_code}.{image_format}"
        s3.put_object(Bucket=S3_DATA_BUCKET, Key=image_s3_key, Body=base64.b64decode(image_base64), ContentType=f"image/{image_format}")

    # DynamoDB登録
    item = {
        "product_id": product_id,
        "product_code": product_code,
        "product_name": event.get("product_name", ""),
        "category": event.get("category", ""),
        "price": event.get("price", 0),
        "text_content": text_content,
        "image_s3_key": image_s3_key,
        "created_at": now,
    }
    product_table.put_item(Item=item)

    # S3 Vectors登録
    metadata = {"product_code": product_code, "product_name": event.get("product_name", ""), "category": event.get("category", "")}
    if image_embedding:
        put_vector(S3_VECTOR_INDEX_IMAGE, product_id, image_embedding, metadata)
    if text_embedding:
        put_vector(S3_VECTOR_INDEX_TEXT, product_id, text_embedding, metadata)

    # OpenSearch登録
    index_to_opensearch(product_id, product_code, event.get("product_name", ""),
                        event.get("category", ""), text_content,
                        image_embedding, text_embedding)

    return {"statusCode": 200, "body": {"product_id": product_id, "status": "registered"}}


def register_batch(s3_prefix, csv_key):
    # CSVを読み込み
    csv_obj = s3.get_object(Bucket=S3_DATA_BUCKET, Key=csv_key)
    csv_content = csv_obj["Body"].read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(csv_content))

    results = []
    for row in reader:
        product_code = row.get("product_code", "").strip()
        if not product_code:
            continue

        product_id = str(uuid.uuid4())
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        # テキストファイル読み込み
        text_content = load_text_from_s3(s3_prefix, product_code)

        # 画像読み込み
        image_bytes, image_format = load_image_from_s3(s3_prefix, product_code)

        # Embedding生成
        text_embedding = embed_text(text_content) if text_content else None
        image_embedding = None
        if image_bytes:
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")
            image_embedding = embed_image(image_b64, image_format)

        # 画像をproducts/images/に保存
        image_s3_key = ""
        if image_bytes:
            image_s3_key = f"products/images/{product_code}.{image_format}"
            s3.put_object(Bucket=S3_DATA_BUCKET, Key=image_s3_key, Body=image_bytes, ContentType=f"image/{image_format}")

        # DynamoDB登録
        item = {
            "product_id": product_id,
            "product_code": product_code,
            "product_name": row.get("product_name", ""),
            "category": row.get("category", ""),
            "price": int(row.get("price", 0)) if row.get("price") else 0,
            "text_content": text_content,
            "image_s3_key": image_s3_key,
            "created_at": now,
        }
        product_table.put_item(Item=item)

        # S3 Vectors登録
        metadata = {"product_code": product_code, "product_name": row.get("product_name", ""), "category": row.get("category", "")}
        if image_embedding:
            put_vector(S3_VECTOR_INDEX_IMAGE, product_id, image_embedding, metadata)
        if text_embedding:
            put_vector(S3_VECTOR_INDEX_TEXT, product_id, text_embedding, metadata)

        # OpenSearch登録
        index_to_opensearch(product_id, product_code, row.get("product_name", ""),
                            row.get("category", ""), text_content,
                            image_embedding, text_embedding)

        results.append({"product_code": product_code, "product_id": product_id, "status": "ok"})

    return {"statusCode": 200, "body": {"registered": len(results), "results": results}}


def load_text_from_s3(s3_prefix, product_code):
    for ext in ["txt", "md"]:
        key = f"{s3_prefix}texts/{product_code}.{ext}"
        try:
            obj = s3.get_object(Bucket=S3_DATA_BUCKET, Key=key)
            return obj["Body"].read().decode("utf-8")
        except s3.exceptions.NoSuchKey:
            continue
    return ""


def load_image_from_s3(s3_prefix, product_code):
    for ext in ["jpg", "jpeg", "png", "webp"]:
        key = f"{s3_prefix}images/{product_code}.{ext}"
        try:
            obj = s3.get_object(Bucket=S3_DATA_BUCKET, Key=key)
            fmt = "jpeg" if ext in ["jpg", "jpeg"] else ext
            return obj["Body"].read(), fmt
        except s3.exceptions.NoSuchKey:
            continue
    return None, None


def embed_text(text):
    body = {
        "taskType": "SINGLE_EMBEDDING",
        "singleEmbeddingParams": {
            "embeddingPurpose": "GENERIC_INDEX",
            "embeddingDimension": EMBEDDING_DIM,
            "text": {"truncationMode": "END", "value": text}
        }
    }
    response = bedrock.invoke_model(body=json.dumps(body), modelId=MODEL_ID, contentType="application/json")
    result = json.loads(response["body"].read())
    return result["embeddings"][0]["embedding"]


def embed_image(image_base64, image_format):
    body = {
        "taskType": "SINGLE_EMBEDDING",
        "singleEmbeddingParams": {
            "embeddingPurpose": "GENERIC_INDEX",
            "embeddingDimension": EMBEDDING_DIM,
            "image": {"format": image_format, "source": {"bytes": image_base64}}
        }
    }
    response = bedrock.invoke_model(body=json.dumps(body), modelId=MODEL_ID, contentType="application/json")
    result = json.loads(response["body"].read())
    return result["embeddings"][0]["embedding"]


def put_vector(index_name, product_id, embedding, metadata):
    s3vectors.put_vectors(
        vectorBucketName=S3_VECTOR_BUCKET,
        indexName=index_name,
        vectors=[{
            "key": product_id,
            "data": {"float32": embedding},
            "metadata": metadata,
        }]
    )


def index_to_opensearch(product_id, product_code, product_name, category, text_content, image_embedding, text_embedding):
    """OpenSearch Serverlessに画像/テキストのembeddingをそれぞれ1ドキュメントとして登録"""
    client = get_os_client()
    if not client:
        return

    base_doc = {
        "product_id": product_id,
        "product_code": product_code,
        "product_name": product_name,
        "category": category,
        "text_content": text_content[:10000],
    }

    try:
        if image_embedding:
            doc = {**base_doc, "embedding": image_embedding, "embedding_type": "image"}
            client.index(index=AOSS_INDEX_NAME, body=doc)
        if text_embedding:
            doc = {**base_doc, "embedding": text_embedding, "embedding_type": "text"}
            client.index(index=AOSS_INDEX_NAME, body=doc)
    except Exception as e:
        print(f"OpenSearch index error: {e}")
