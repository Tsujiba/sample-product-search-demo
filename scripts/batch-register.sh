#!/bin/bash
# S3上の商品データをバッチ登録
# Usage: ./scripts/batch-register.sh <s3-prefix>
#   例: ./scripts/batch-register.sh upload/batch001/

set -e
S3_PREFIX=${1:?Usage: $0 <s3-prefix>}
REGION=${AWS_DEFAULT_REGION:-us-east-1}
LAMBDA="nova-mme-product-register"

echo "=== バッチ登録: s3_prefix=${S3_PREFIX} ==="

PAYLOAD=$(echo "{\"s3_prefix\": \"${S3_PREFIX}\"}" | base64)
aws lambda invoke --function-name "$LAMBDA" --payload "$PAYLOAD" \
  --region "$REGION" --cli-read-timeout 900 /tmp/batch-register-out.json 2>&1

cat /tmp/batch-register-out.json | python3 -m json.tool 2>/dev/null || cat /tmp/batch-register-out.json
echo ""
echo "=== 完了 ==="
