# 商品マルチモーダル検索デモ

Amazon Nova Multimodal Embeddings を活用した商品検索プロトタイプ。テキスト・画像によるマルチモーダル検索を、2つのベクトルストア構成で比較検証できます。

## 概要

| 構成 | バックエンド | 検索方式 | コスト |
|---|---|---|---|
| **構成A** | S3 Vectors + DynamoDB | ベクトル類似度検索 | 従量課金（数ドル/月） |
| **構成B** | OpenSearch Serverless + DynamoDB | ハイブリッド検索（knn + BM25） | 最低$175/月 |

同一UIから両構成を切り替え、または並列比較して検索精度を評価できます。

## アーキテクチャ

### 構成A: S3 Vectors

```
クエリ → Nova Embeddings → S3 Vectors (cosine knn) → DynamoDB → レスポンス
```

### 構成B: OpenSearch Serverless

```
クエリ → Nova Embeddings → OpenSearch (knn 60% + BM25 40% hybrid) → DynamoDB → レスポンス
```

- Embedding: Amazon Nova Multimodal Embeddings V1（1024次元）
- 日本語解析: kuromoji tokenizer（構成B）
- 冗長化: StandbyReplicas DISABLED（コスト最適化）

詳細は [docs/](./docs/) を参照。

## 機能

- **商品登録**: 単品登録 / CSV + 画像バッチ登録
- **マルチモーダル検索**: テキスト検索 / 画像検索
- **精度比較UI**: S3 Vectors と OpenSearch の結果を左右並列表示
- **バックエンド切替**: 検索時にバックエンドを選択可能

## 前提条件

- AWS アカウント（Bedrock Nova Embeddings が有効なリージョン）
- Node.js 20+, Python 3.13+, AWS CDK v2
- Amazon Bedrock で `amazon.nova-2-multimodal-embeddings-v1:0` モデルへのアクセスを有効化

## デプロイ

```bash
cd deployment
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export CDK_DEFAULT_ACCOUNT=<your-account-id>
export CDK_DEFAULT_REGION=us-east-1
export CDK_INPUT_USER_EMAILS=<your-email>

npx cdk bootstrap

# Lambda Layer をビルド＆S3にアップロード（初回のみ）
# データバケット名: nova-mme-<account-id>-<region>
../scripts/build-opensearch-layer.sh nova-mme-${CDK_DEFAULT_ACCOUNT}-${CDK_DEFAULT_REGION}

npx cdk deploy --all
```

デプロイ完了後、出力される `WebsiteURL` にアクセスし、Cognito で作成されたユーザーでログインしてください。

## プロジェクト構成

```
deployment/
  product_service/       # 商品検索サービス CDK スタック
  nova_service/          # Nova MME サービス CDK スタック
  frontend/              # フロントエンド CDK スタック
source/
  product_service/lambda/
    product-register/    # 商品登録 Lambda
    product-search/      # 商品検索 Lambda（S3 Vectors / OpenSearch 切替）
    product-list/        # 商品一覧 Lambda
  frontend/web/          # React フロントエンド（Cloudscape Design）
docs/
  architecture-s3vectors.md    # 構成A 設計
  architecture-opensearch.md   # 構成B 設計
  comparison-and-tuning.md     # 比較評価・チューニング観点
scripts/
  clear-all-products.sh        # 全商品データ削除スクリプト
```

## 商品データ登録

### 単品登録

フロントエンドの「Products」→「登録」タブから GUI で登録。

### バッチ登録

S3 に以下の構造でアップロード後、スクリプトで登録：

```
s3://<data-bucket>/upload/batch001/
  products.csv          # product_code, product_name, category, price
  texts/P00001.txt      # 商品説明テキスト
  images/P00001.jpeg    # 商品画像
```

```bash
aws s3 sync ./sample_data s3://<data-bucket>/upload/batch001/
./scripts/batch-register.sh upload/batch001/
```

## スクリプト

```bash
# 商品バッチ登録
./scripts/batch-register.sh upload/batch001/

# 全商品データ削除（S3 Vectors + DynamoDB + OpenSearch）
./scripts/clear-all-products.sh

# OpenSearch インデックス再作成（analyzer変更時等）
./scripts/recreate-opensearch-index.sh

# opensearch-py Lambda Layer ビルド＆アップロード（初回のみ）
./scripts/build-opensearch-layer.sh nova-mme-<account-id>-<region>
```

## クリーンアップ

```bash
cd deployment
npx cdk destroy --all
```

## ドキュメント

- [構成A: S3 Vectors 設計](./docs/architecture-s3vectors.md)
- [構成B: OpenSearch Serverless 設計](./docs/architecture-opensearch.md)
- [比較評価・チューニング](./docs/comparison-and-tuning.md)
- [元のNova MMEデモ README](./README_origin.md)
