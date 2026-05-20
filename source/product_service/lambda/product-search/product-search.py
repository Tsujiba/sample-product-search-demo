"""
product-search: 商品検索Lambda
- テキスト/画像クエリをEmbedding化 → S3 Vectors検索 → DynamoDB結合
- 将来的にbackendパラメータでOpenSearch切替対応
"""
import json
import boto3
import os
import base64

DYNAMO_PRODUCT_TABLE = os.environ["DYNAMO_PRODUCT_TABLE"]
S3_DATA_BUCKET = os.environ["S3_DATA_BUCKET"]
S3_VECTOR_BUCKET = os.environ["S3_VECTOR_BUCKET"]
S3_VECTOR_INDEX_IMAGE = os.environ["S3_VECTOR_INDEX_IMAGE"]
S3_VECTOR_INDEX_TEXT = os.environ["S3_VECTOR_INDEX_TEXT"]
MODEL_ID = os.environ["MODEL_ID"]
EMBEDDING_DIM = int(os.environ.get("EMBEDDING_DIM", "1024"))
S3_PRESIGNED_URL_EXPIRY_S = int(os.environ.get("S3_PRESIGNED_URL_EXPIRY_S", "3600"))

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
bedrock = boto3.client("bedrock-runtime")
s3vectors = boto3.client("s3vectors")

product_table = dynamodb.Table(DYNAMO_PRODUCT_TABLE)


def lambda_handler(event, context):
    """
    入力:
    {
      "query_text": "もこもこの靴下",
      "query_image_base64": "",
      "query_image_format": "jpeg",
      "backend": "s3vectors",          # "s3vectors" | "opensearch" | "both"
      "search_targets": ["image", "text"],  # 検索対象インデックス
      "top_k": 10,
      "include_image_url": true
    }
    """
    query_text = event.get("query_text", "").strip()
    query_image_b64 = event.get("query_image_base64", "")
    query_image_format = event.get("query_image_format", "jpeg")
    backend = event.get("backend", "s3vectors")
    search_targets = event.get("search_targets", ["image", "text"])
    top_k = event.get("top_k", 10)
    include_image_url = event.get("include_image_url", True)

    if not query_text and not query_image_b64:
        return {"statusCode": 400, "body": {"error": "query_text or query_image_base64 is required"}}

    # クエリのEmbedding生成
    query_embedding = None
    if query_image_b64:
        query_embedding = embed_image(query_image_b64, query_image_format)
    elif query_text:
        query_embedding = embed_text(query_text)

    if not query_embedding:
        return {"statusCode": 500, "body": {"error": "Failed to generate query embedding"}}

    # バックエンド別検索
    if backend == "s3vectors":
        results = search_s3vectors(query_embedding, search_targets, top_k)
    else:
        # Phase 2: opensearch対応
        results = search_s3vectors(query_embedding, search_targets, top_k)

    # DynamoDBから商品詳細を取得 & presigned URL付与
    enriched = enrich_results(results, include_image_url)

    return {"statusCode": 200, "body": {"results": enriched, "query_text": query_text, "backend": backend}}


def search_s3vectors(query_embedding, search_targets, top_k):
    """S3 Vectorsで画像/テキストインデックスを検索し、結果をマージ"""
    all_results = {}

    for target in search_targets:
        index_name = S3_VECTOR_INDEX_IMAGE if target == "image" else S3_VECTOR_INDEX_TEXT
        response = s3vectors.query_vectors(
            vectorBucketName=S3_VECTOR_BUCKET,
            indexName=index_name,
            queryVector={"float32": query_embedding},
            topK=top_k,
            returnDistance=True,
            returnMetadata=True,
        )
        for vec in response.get("vectors", []):
            product_id = vec["key"]
            distance = vec.get("distance", 1.0)
            # 同一商品が複数インデックスにヒットした場合、最小距離を採用
            if product_id not in all_results or distance < all_results[product_id]["distance"]:
                all_results[product_id] = {
                    "product_id": product_id,
                    "distance": distance,
                    "match_type": target,
                    "metadata": vec.get("metadata", {}),
                }

    # 距離でソート（小さい = 類似度高い）
    sorted_results = sorted(all_results.values(), key=lambda x: x["distance"])
    return sorted_results[:top_k]


def enrich_results(results, include_image_url):
    """DynamoDBから商品詳細を取得し、presigned URLを付与"""
    enriched = []
    for item in results:
        product_id = item["product_id"]
        db_item = product_table.get_item(Key={"product_id": product_id}).get("Item")
        if not db_item:
            continue

        result = {
            "product_id": product_id,
            "product_code": db_item.get("product_code", ""),
            "product_name": db_item.get("product_name", ""),
            "category": db_item.get("category", ""),
            "price": int(db_item.get("price", 0)),
            "text_content": db_item.get("text_content", "")[:200],  # プレビュー用に先頭200文字
            "distance": item["distance"],
            "match_type": item["match_type"],
        }

        if include_image_url and db_item.get("image_s3_key"):
            result["image_url"] = s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": S3_DATA_BUCKET, "Key": db_item["image_s3_key"]},
                ExpiresIn=S3_PRESIGNED_URL_EXPIRY_S,
            )

        enriched.append(result)

    return enriched


def embed_text(text):
    body = {
        "taskType": "SINGLE_EMBEDDING",
        "singleEmbeddingParams": {
            "embeddingPurpose": "GENERIC_RETRIEVAL",
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
            "embeddingPurpose": "GENERIC_RETRIEVAL",
            "embeddingDimension": EMBEDDING_DIM,
            "image": {"format": image_format, "source": {"bytes": image_base64}}
        }
    }
    response = bedrock.invoke_model(body=json.dumps(body), modelId=MODEL_ID, contentType="application/json")
    result = json.loads(response["body"].read())
    return result["embeddings"][0]["embedding"]
