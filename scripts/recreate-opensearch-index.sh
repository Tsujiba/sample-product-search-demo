#!/bin/bash
# OpenSearchインデックスを削除→再作成するスクリプト
# search pipeline + kuromoji analyzer 付きで再作成される
# Usage: ./scripts/recreate-opensearch-index.sh

set -e
REGION=${AWS_DEFAULT_REGION:-us-east-1}
LAMBDA="nova-mme-aoss-provision-index"

echo "=== OpenSearch インデックス再作成 ==="

# 一時的にrecreateコードをデプロイ
cat > /tmp/recreate_index.py << 'SCRIPT'
import json, os, time, boto3
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

def on_event(event, context):
    endpoint = os.environ["AOSS_ENDPOINT"].replace("https://", "")
    index_name = os.environ["AOSS_INDEX_NAME"]
    dim = int(os.environ["EMBEDDING_DIM"])
    credentials = boto3.Session().get_credentials()
    auth = AWS4Auth(credentials.access_key, credentials.secret_key, os.environ.get("AWS_REGION", "us-east-1"), "aoss", session_token=credentials.token)
    client = OpenSearch(hosts=[{"host": endpoint, "port": 443}], http_auth=auth, use_ssl=True, verify_certs=True, connection_class=RequestsHttpConnection, timeout=30)

    try:
        client.indices.delete(index=index_name)
        time.sleep(2)
    except Exception as e:
        print(f"Delete note: {e}")

    pipeline_body = {"description": "Hybrid search normalization", "phase_results_processors": [{"normalization-processor": {"normalization": {"technique": "min_max"}, "combination": {"technique": "arithmetic_mean", "parameters": {"weights": [0.6, 0.4]}}}}]}
    try:
        client.http.put("/_search/pipeline/hybrid-search-pipeline", body=pipeline_body)
    except Exception as e:
        print(f"Pipeline note: {e}")

    body = {"settings": {"index": {"knn": True}, "analysis": {"analyzer": {"ja_analyzer": {"type": "custom", "tokenizer": "kuromoji_tokenizer", "filter": ["kuromoji_baseform", "kuromoji_part_of_speech", "lowercase"]}}}}, "mappings": {"properties": {"embedding": {"type": "knn_vector", "dimension": dim, "method": {"engine": "faiss", "name": "hnsw", "space_type": "cosinesimil"}}, "product_id": {"type": "keyword"}, "product_code": {"type": "keyword"}, "product_name": {"type": "text", "analyzer": "ja_analyzer"}, "category": {"type": "keyword"}, "text_content": {"type": "text", "analyzer": "ja_analyzer"}, "embedding_type": {"type": "keyword"}}}}
    client.indices.create(index=index_name, body=body)
    return {"statusCode": 200, "body": f"Recreated index {index_name} with kuromoji + hybrid pipeline"}
SCRIPT

cd /tmp && zip -j recreate_index.zip recreate_index.py
ORIG_HANDLER=$(aws lambda get-function-configuration --function-name "$LAMBDA" --region "$REGION" --query "Handler" --output text)

aws lambda update-function-code --function-name "$LAMBDA" --zip-file fileb:///tmp/recreate_index.zip --region "$REGION" --output text > /dev/null
sleep 8
aws lambda update-function-configuration --function-name "$LAMBDA" --handler "recreate_index.on_event" --region "$REGION" --output text > /dev/null
sleep 8

RESULT=$(aws lambda invoke --function-name "$LAMBDA" --payload $(echo '{}' | base64) --region "$REGION" /tmp/recreate-result.json 2>&1)
cat /tmp/recreate-result.json

# 元に戻す
aws lambda update-function-configuration --function-name "$LAMBDA" --handler "$ORIG_HANDLER" --region "$REGION" --output text > /dev/null
echo ""
echo "=== 完了 ==="
