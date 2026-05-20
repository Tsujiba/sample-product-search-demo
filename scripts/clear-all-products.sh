#!/bin/bash
# 全商品データを削除するスクリプト（S3 Vectors + DynamoDB + OpenSearch）
# Usage: ./scripts/clear-all-products.sh

set -e
REGION="us-east-1"
TABLE="nova_mme_product_master"
VECTOR_BUCKET="nova-mme-vector-bucket"
PROVISION_LAMBDA="nova-mme-aoss-provision-index"

echo "=== 商品データ全削除 ==="

# 1. DynamoDB + S3 Vectors
PIDS=$(aws dynamodb scan --table-name "$TABLE" --region "$REGION" \
  --projection-expression "product_id" --query "Items[*].product_id.S" --output text)

if [ -z "$PIDS" ]; then
  echo "DynamoDB: 商品なし"
else
  COUNT=0
  for PID in $PIDS; do
    aws s3vectors delete-vectors --vector-bucket-name "$VECTOR_BUCKET" --index-name product-image-vectors --keys "$PID" --region "$REGION" 2>/dev/null || true
    aws s3vectors delete-vectors --vector-bucket-name "$VECTOR_BUCKET" --index-name product-text-vectors --keys "$PID" --region "$REGION" 2>/dev/null || true
    aws dynamodb delete-item --table-name "$TABLE" --key "{\"product_id\":{\"S\":\"$PID\"}}" --region "$REGION"
    COUNT=$((COUNT + 1))
  done
  echo "S3 Vectors + DynamoDB: ${COUNT}件削除"
fi

# 2. OpenSearch (インデックス再作成で全ドキュメント削除)
echo "OpenSearch: インデックス再作成中..."
ORIG_HANDLER=$(aws lambda get-function-configuration --function-name "$PROVISION_LAMBDA" --region "$REGION" --query "Handler" --output text)
aws lambda update-function-configuration --function-name "$PROVISION_LAMBDA" --handler "recreate_index.on_event" --region "$REGION" --output text > /dev/null 2>&1
sleep 8
RESULT=$(aws lambda invoke --function-name "$PROVISION_LAMBDA" --payload $(echo '{}' | base64) --region "$REGION" /dev/stdout 2>/dev/null | head -1)
aws lambda update-function-configuration --function-name "$PROVISION_LAMBDA" --handler "$ORIG_HANDLER" --region "$REGION" --output text > /dev/null 2>&1
echo "OpenSearch: 完了"

echo "=== 全削除完了 ==="
