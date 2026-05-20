# Amazon Nova マルチモーダルエンベディング（MME）デモ + 商品画像検索拡張

> このソリューションは CDK パッケージとして提供されており、いくつかのスクリプトを実行するだけで AWS アカウントにデプロイできます。

このアプリケーションは、[**Amazon Bedrock**](https://aws.amazon.com/bedrock/) における [**Amazon Nova マルチモーダルエンベディング**](https://aws.amazon.com/blogs/aws/amazon-nova-multimodal-embeddings-now-available-in-amazon-bedrock/) の機能をデモンストレーションするものです。テキスト、画像、動画、音声を横断した統合検索を実現します。

さらに本プロジェクトでは、Nova MME を活用した **商品画像検索機能**（Product Service）を拡張実装しています。CSV + 画像ファイルによる商品一括登録、テキスト/画像によるマルチモーダル商品検索が可能です。

## 目次

- [デモ動画](#デモ動画)
- [アーキテクチャ](#アーキテクチャ)
- [商品画像検索拡張（Product Service）](#商品画像検索拡張product-service)
- [前提条件](#前提条件)
- [デプロイ手順](#デプロイ手順)
- [デプロイの確認](#デプロイの確認)
- [使い方](#使い方)
- [クリーンアップ](#クリーンアップ)

## デモ動画
![nova-mme-demo](./assets/nova-mme-demo.gif)

## アーキテクチャ

Nova MME は、スケーラビリティ・信頼性・パフォーマンスを備えた AWS サーバーレスアーキテクチャ上に構築されています。

![システムアーキテクチャ](./assets/nova-mme-architecture.png)

### コアコンポーネント

| コンポーネント | 技術 | 用途 |
|---|---|---|
| フロントエンド | React + Cloudscape Design | メディアアップロード・検索UI |
| 認証 | Amazon Cognito (User Pool + Identity Pool) | ユーザー認証 |
| API | Amazon API Gateway + AWS Lambda (Python) | REST API |
| ベクトルストア | Amazon S3 Vectors | Embedding の保存・類似検索 |
| メタデータ | Amazon DynamoDB | タスク管理・商品マスタ |
| Embedding 生成 | Amazon Bedrock (Nova Multimodal Embeddings) | クロスモーダル Embedding 生成 |
| ホスティング | Amazon CloudFront + S3 | 静的 Web サイト配信 |
| IaC | AWS CDK (Python) | インフラデプロイ |

### マルチモーダルエンベディング処理

![マルチモーダルエンベディング処理](./assets/mme-diagram.png)

異なるコンテンツタイプを共有ベクトル空間に変換し、テキストで画像を検索したり、画像で類似商品を発見するクロスモーダル検索を実現します。

## 商品画像検索拡張（Product Service）

既存の Nova MME デモを「**商品画像検索ツール**」に特化させた拡張機能です。

### 構成：S3 Vectors + DynamoDB

```
┌─────────────────────────────────────────────────────────────────┐
│  React Frontend (Cloudscape)                                     │
│  - 商品登録画面（CSV + 画像アップロード）                         │
│  - 検索画面（テキスト/画像クエリ）                                │
└──────────────────────────────┬──────────────────────────────────┘
                               │ API Gateway + Cognito Auth
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  Lambda Functions (Python 3.13)                                   │
│  product-register:  商品データ登録（Embedding生成 + 保存）        │
│  product-search:    マルチモーダル検索                            │
│  product-list:      商品一覧取得                                 │
└───────────┬──────────────────┬──────────────────┬───────────────┘
            │                  │                  │
            ▼                  ▼                  ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ S3 Vectors       │  │ S3 Vectors       │  │ DynamoDB         │
│ product-image    │  │ product-text     │  │ product-master   │
│ -vectors         │  │ -vectors         │  │ (商品マスタ)     │
│ (画像Embedding)  │  │ (テキスト       │  │                  │
│                  │  │  Embedding)      │  │                  │
└──────────────────┘  └──────────────────┘  └──────────────────┘
```

### 主な機能

- **商品一括登録**: CSV ファイル + 画像ファイルで商品データを一括登録
- **マルチモーダル検索**: テキストクエリ（例：「もこもこの靴下」）や画像クエリで商品を検索
- **クロスモーダル検索**: テキストで画像を、画像でテキストを横断検索（同一ベクトル空間）

### 使用モデル

| モデル | 用途 |
|---|---|
| `amazon.nova-2-multimodal-embeddings-v1:0` | テキスト/画像の Embedding 生成（1024次元） |
| Nova Lite 1.0 | メディア処理補助 |

### API エンドポイント

| メソッド | パス | 説明 |
|---|---|---|
| POST | `/v1/products/register` | 商品登録（CSV + 画像） |
| POST | `/v1/products/search` | 商品検索（テキスト/画像クエリ） |
| POST | `/v1/products/list` | 商品一覧取得 |

### データモデル

**DynamoDB: product-master テーブル**

| 属性 | 型 | 説明 |
|---|---|---|
| product_id (PK) | String | 商品ID |
| product_code | String | 商品コード（GSI） |
| product_name | String | 商品名 |
| category | String | カテゴリ（GSI） |
| price | Number | 価格 |
| image_s3_key | String | S3 上の画像パス |
| full_text | String | 全テキスト情報 |

## 前提条件

- AWS アカウントの管理者アクセス、または必要なリソースを作成・管理する [IAM](https://aws.amazon.com/iam/) 権限
- Amazon Bedrock で以下のモデルへのアクセスを有効化：
    - Nova Multimodal Embeddings
    - Nova Lite 1.0

### 環境依存関係のインストールと認証設定

<details><summary>
:bulb: CloudShell を使用する場合はスキップ可能。ローカル環境の場合に必要です。
</summary>

- [ ] Node.js のインストール: https://nodejs.org/en/download/
- [ ] Python 3.9+ のインストール: https://www.python.org/downloads/
- [ ] Git のインストール: https://github.com/git-guides/install-git
- [ ] Pip のインストール
```sh
python -m ensurepip --upgrade
```
- [ ] Python 仮想環境のインストール
```sh
pip install virtualenv
```
- [ ] AWS CLI 認証の設定
```sh
aws configure
```
</details>

![CloudShell を開く](./assets/cloudshell.png)

### 対応リージョン

|||||
---------- | ---------- | ---------- | ---------- |
US | us-east-1 (バージニア北部) | ||

## デプロイ手順

1. ソースコードをクローン

```bash
git clone https://github.com/aws-samples/sample-demo-of-nova-mme.git
cd sample-demo-of-nova-mme
```

2. 環境変数を設定

```bash
# Web ポータルのログイン用メールアドレス（カンマ区切りで複数指定可）
export CDK_INPUT_USER_EMAILS=<メールアドレス>

# デプロイ先の AWS アカウント ID とリージョン
export CDK_DEFAULT_ACCOUNT=<アカウントID>
export CDK_DEFAULT_REGION=<リージョン>  # 例: us-east-1
```

3. デプロイスクリプトを実行

```bash
cd deployment
bash ./deploy-cloudshell.sh
```

## デプロイの確認

デプロイ完了後、Web サイトの URL がコンソールに表示されます。CloudFormation コンソールの **NovaMmeRootStack** スタックの出力からも確認できます。

出力される主な情報：
- **Website URL**: フロントエンドの URL
- **API Gateway Base URL: Nova MME Service**: Nova MME サービスの API エンドポイント
- **API Gateway Base URL: Product Service**: 商品検索サービスの API エンドポイント

## 使い方

- デプロイ時に `CDK_INPUT_USER_EMAILS` で指定したメールアドレスに、ユーザー名と一時パスワードが送信されます。これを使って Web ポータルにサインインしてください。
- メールアドレスを指定しなかった場合は、Cognito コンソールから **nova-mme-user-pool** にユーザーを手動で作成してください。

## プロジェクト構成

```
sample-product-search-demo/
├── source/
│   ├── product_service/              # 商品検索サービス（拡張）
│   │   └── lambda/
│   │       ├── product-register/     # 商品登録 Lambda
│   │       ├── product-search/       # 商品検索 Lambda
│   │       └── product-list/         # 商品一覧 Lambda
│   ├── nova_service/                 # Nova MME サービス（既存）
│   │   └── lambda/
│   └── frontend/web/                 # React フロントエンド
│
├── deployment/
│   ├── app.py                        # CDK アプリケーション（ルートスタック）
│   ├── product_service/              # 商品検索 CDK スタック（拡張）
│   ├── nova_service/                 # Nova MME CDK スタック
│   ├── pre_stack/                    # 事前準備スタック（S3, Cognito, Lambda Layer）
│   ├── post_stack/                   # 事後処理スタック（ユーザー作成）
│   └── frontend/                     # フロントエンド CDK スタック
│
├── docs/
│   └── implementation-plan.md        # 実装プラン
└── assets/                           # ドキュメント用画像
```

## コスト見積もり（5万件の商品データ）

| サービス | 月額見積もり |
|---|---|
| S3 Vectors（2インデックス × 5万ベクトル） | ~$5-10 |
| DynamoDB（5万レコード、オンデマンド） | ~$5-10 |
| Lambda（検索 + 登録） | ~$1-5 |
| Bedrock Nova Embeddings（初期登録 + 検索） | ~$10-20 |
| **合計** | **~$20-45/月** |

## クリーンアップ

実験が終わったら、CloudShell から以下のコマンドでリソースを削除してください：

```bash
cdk destroy
```

CloudFormation コンソールから `NovaMmeRootStack` スタックを選択して削除することもできます。

## ライセンス

このプロジェクトは MIT-0 ライセンスの下で公開されています。詳細は [LICENSE](LICENSE) ファイルを参照してください。
