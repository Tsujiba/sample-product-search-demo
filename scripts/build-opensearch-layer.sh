#!/bin/bash
# Lambda Layer (opensearch-py + requests-aws4auth) をビルドしてS3にアップロード
# Usage: ./scripts/build-opensearch-layer.sh <s3-bucket-name>
#   例: ./scripts/build-opensearch-layer.sh nova-mme-082888215689-us-east-1

set -e
BUCKET=${1:?Usage: $0 <s3-bucket-name>}
REGION=${AWS_DEFAULT_REGION:-us-east-1}

echo "=== Building opensearch Lambda Layer ==="
TMPDIR=$(mktemp -d)
mkdir -p "$TMPDIR/python"
pip install opensearch-py requests-aws4auth -t "$TMPDIR/python" --quiet
cd "$TMPDIR" && zip -r opensearch_layer.zip python -q
aws s3 cp opensearch_layer.zip "s3://$BUCKET/layer/opensearch_layer.zip" --region "$REGION"
rm -rf "$TMPDIR"
echo "=== Uploaded to s3://$BUCKET/layer/opensearch_layer.zip ==="
