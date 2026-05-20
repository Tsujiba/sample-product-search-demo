# 商品画像検索ソリューション拡張 - 実装プラン

**作成日**: 2026-05-20  
**ベースプロジェクト**: sample-demo-of-nova-mme（既存のマルチモーダル検索デモ）

---

## 1. 現状分析

### 既存ソリューションの構成

| コンポーネント | 技術 | 用途 |
|---|---|---|
| フロントエンド | React + Cloudscape Design | メディアアップロード・検索UI |
| 認証 | Cognito User Pool + Identity Pool | ユーザー認証 |
| API | API Gateway + Lambda (Python) | REST API |
| ベクトルストア | S3 Vectors | 動画/画像/音声/テキストのEmbedding保存・検索 |
| メタデータ | DynamoDB | タスク管理（アップロード情報） |
| Embedding | Nova Multimodal Embeddings v1 (1024次元) | クロスモーダルEmbedding生成 |
| IaC | CDK (Python) | インフラデプロイ |

### 既存の検索フロー

1. ユーザーがテキスト or 画像でクエリ入力
2. Lambda が Nova Embeddings でクエリをベクトル化（`GENERIC_RETRIEVAL`）
3. S3 Vectors で類似ベクトル検索（`query_vectors`）
4. DynamoDB からタスクメタデータ取得
5. S3 presigned URL 付きで結果返却

### 拡張に活用できる既存資産

- S3 Vectors のバケット・インデックス作成パイプライン
- Nova Embeddings の呼び出しロジック（テキスト/画像別々）
- Cognito 認証基盤
- CloudFront + S3 のフロントエンドホスティング
- CDK ネストスタック構成

---

## 2. 拡張の目的

既存のマルチモーダルデモを「**商品画像検索ツール**」に特化させ、以下を実現する：

1. **商品データの一括登録**（CSV + 画像ファイル）
2. **マルチモーダル検索**（テキスト/画像クエリ → 商品検索）
3. **構成A/B の切り替え・精度比較**（同一UIで両バックエンドを検証）

---

## 3. アーキテクチャ設計

### 3-1. 構成A：S3 Vectors + DynamoDB（Phase 1 で実装）

```
┌─────────────────────────────────────────────────────────────────┐
│  React Frontend (Cloudscape)                                     │
│  - 商品登録画面（CSV + 画像アップロード）                         │
│  - 検索画面（テキスト/画像クエリ、バックエンド切替トグル）         │
└──────────────────────────────┬──────────────────────────────────┘
                               │ API Gateway + Cognito Auth
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  Lambda Functions (Python)                                       │
│                                                                  │
│  product-register:  商品データ登録（Embedding生成 + 保存）        │
│  product-search:    検索オーケストレーション                      │
│  product-list:      商品一覧取得                                 │
└───────────┬──────────────────┬──────────────────┬───────────────┘
            │                  │                  │
            ▼                  ▼                  ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ S3 Vectors       │  │ S3 Vectors       │  │ DynamoDB         │
│ product-images   │  │ product-texts    │  │ product-master   │
│ (画像Embedding)  │  │ (テキスト       │  │ (商品マスタ)     │
│                  │  │  Embedding)      │  │ PK: product_id   │
│ key=product_id   │  │ key=product_id   │  │ GSI: code, name  │
└──────────────────┘  └──────────────────┘  └──────────────────┘
```

### 3-2. 構成B：OpenSearch Serverless（Phase 2 で追加）

```
┌─────────────────────────────────────────────────────────────────┐
│  同一 React Frontend                                             │
│  - バックエンド切替: "S3 Vectors" | "OpenSearch"                 │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  product-search Lambda                                           │
│  - backend パラメータで分岐                                      │
│    - "s3vectors" → 既存の S3 Vectors 検索                       │
│    - "opensearch" → OpenSearch Serverless 検索                   │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  OpenSearch Serverless Collection                                 │
│  - knn_vector: image_vector (1024d), text_vector (1024d)         │
│  - text (kuromoji): product_name, description, full_text         │
│  - keyword: product_code, material, origin                       │
│  - ハイブリッド検索（ベクトル + 全文検索）                        │
└─────────────────────────────────────────────────────────────────┘
```

### 3-3. 精度比較機能

```
検索結果画面:
┌─────────────────────────────────────────────────────────────┐
│ クエリ: "もこもこの靴下"                                     │
│                                                              │
│ [S3 Vectors] | [OpenSearch] | [並列比較]  ← タブ切替        │
│                                                              │
│ ┌─────────────────────┐  ┌─────────────────────┐           │
│ │ S3 Vectors 結果     │  │ OpenSearch 結果     │           │
│ │ Score: 0.92         │  │ Score: 0.95         │           │
│ │ 商品A: もこもこ...  │  │ 商品A: もこもこ...  │           │
│ │ 商品B: ふわふわ...  │  │ 商品C: あったか...  │           │
│ └─────────────────────┘  └─────────────────────┘           │
│                                                              │
│ レイテンシー: S3V=120ms / OS=85ms                           │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. 入力データ形式

### 商品データの投入方法

```
S3 アップロード構成:
  upload/
    ├── products.csv              ← 基本情報（商品コード,商品名,カテゴリ,価格）
    ├── images/
    │   ├── A00001.jpg
    │   ├── A00002.jpg
    │   └── ...
    └── texts/
        ├── A00001.txt (or .md)   ← 商品テキスト情報（全文）
        ├── A00002.txt
        └── ...
```

### テキストファイル形式（例）

```
◆キャッチコピー・商品説明
旅行好きプランナーが作った、スーツケースみたいなやわらかボストンバッグ
― シリーズ累計販売数 1.8万個 突破 ―
国内旅行が大好きで...（商品説明全文）

◆仕様・その他注意事項
■素材/外生地：ナイロン100％...
■サイズ/縦約36cm...
```

### 処理フロー

1. CSV から基本情報（product_code, name, category, price）を読み取り
2. `texts/{product_code}.txt` を読み込み → **全文をそのまま Nova Embeddings でベクトル化**（8,192文字以内）
3. `images/{product_code}.jpg` を読み込み → Nova Embeddings で画像ベクトル化
4. DynamoDB に商品マスタ登録（基本情報 + テキスト全文）
5. S3 Vectors に画像ベクトル・テキストベクトルをそれぞれ登録

### テキスト情報の活用

| 構成 | テキストの使い方 |
|---|---|
| 構成A (S3 Vectors) | 全文をEmbedding化 → セマンティック検索のみ |
| 構成B (OpenSearch) | Embedding + kuromoji全文検索 + keyword検索（素材・サイズ等を構造化抽出） |

構成Bでは、テキストから「素材」「サイズ」「重さ」等を正規表現で抽出してフィルタ用フィールドに格納することも可能。

---

## 5. データモデル

### DynamoDB: product-master テーブル

| 属性 | 型 | 説明 |
|---|---|---|
| product_id (PK) | String | 商品ID（UUID or 商品コード） |
| product_code | String | 商品コード（例: A00001） |
| product_name | String | 商品名 |
| description | String | 商品説明文 |
| material | String | 素材 |
| origin | String | 産地 |
| price | Number | 価格 |
| category | String | カテゴリ |
| image_s3_key | String | S3上の画像パス |
| full_text | String | 全テキスト情報（検索用に結合） |
| created_at | String | 登録日時 |

**GSI:**
- `product_code-index`: product_code (PK) → コード完全一致検索用
- `category-index`: category (PK), created_at (SK) → カテゴリ絞り込み用

### S3 Vectors インデックス

| インデックス名 | 次元 | key | metadata |
|---|---|---|---|
| product-image-vectors | 1024 | product_id | product_code, product_name, category |
| product-text-vectors | 1024 | product_id | product_code, product_name, category |

---

## 5. API 設計

### 商品登録

```
POST /products/register
Content-Type: multipart/form-data

Body:
  - csv_file: 商品情報CSV
  - images: 画像ファイル群（ファイル名 = product_code.jpg）

Response: { "task_id": "xxx", "status": "processing", "total": 50000 }
```

### 商品検索

```
POST /products/search
Content-Type: application/json

Body:
{
  "query_text": "もこもこの靴下",      // テキストクエリ（任意）
  "query_image_base64": "...",          // 画像クエリ（任意）
  "backend": "s3vectors",              // "s3vectors" | "opensearch" | "both"
  "search_mode": "semantic",           // "semantic" | "keyword" | "hybrid"
  "top_k": 20,
  "filters": {
    "category": "靴下",
    "price_max": 2000
  }
}

Response:
{
  "results": {
    "s3vectors": {
      "items": [...],
      "latency_ms": 120
    },
    "opensearch": {          // Phase 2 で追加
      "items": [...],
      "latency_ms": 85
    }
  }
}
```

### 商品一覧

```
GET /products?page=1&limit=20&category=靴下
```

---

## 6. 実装フェーズ

### Phase 1: 構成A（S3 Vectors + DynamoDB）

| # | タスク | 詳細 |
|---|---|---|
| 1-1 | CDK: 商品マスタ DynamoDB テーブル追加 | product-master テーブル + GSI |
| 1-2 | CDK: S3 Vectors インデックス追加 | product-image-vectors, product-text-vectors |
| 1-3 | Lambda: product-register | CSV解析 → 画像/テキストEmbedding生成 → S3 Vectors + DynamoDB 登録 |
| 1-4 | Lambda: product-search | テキスト/画像クエリ → Embedding → S3 Vectors検索 → DynamoDB結合 |
| 1-5 | Lambda: product-list | DynamoDB scan/query（ページネーション付き） |
| 1-6 | API Gateway: エンドポイント追加 | /products/register, /products/search, /products |
| 1-7 | Frontend: 商品登録画面 | CSV + 画像アップロードUI |
| 1-8 | Frontend: 商品検索画面 | テキスト/画像入力 + 結果表示（商品カード形式） |
| 1-9 | サンプルデータ作成 | テスト用商品CSV + 画像セット（10-50件） |

### Phase 2: 構成B 追加（OpenSearch Serverless）

| # | タスク | 詳細 |
|---|---|---|
| 2-1 | CDK: OpenSearch Serverless Collection 追加 | ベクトル検索コレクション + kuromoji |
| 2-2 | Lambda: opensearch-indexer | 商品登録時に OpenSearch にも同時インデックス |
| 2-3 | Lambda: product-search 拡張 | backend="opensearch" 分岐追加、ハイブリッド検索 |
| 2-4 | Frontend: バックエンド切替UI | トグル/タブで S3 Vectors / OpenSearch / 並列比較 |
| 2-5 | Frontend: 精度比較ダッシュボード | レイテンシー、スコア分布、結果差分の可視化 |

---

## 7. ディレクトリ構成（追加分）

```
sample-product-search-demo/
├── source/
│   ├── product_service/              # 新規: 商品検索サービス
│   │   └── lambda/
│   │       ├── product-register/     # 商品登録Lambda
│   │       │   ├── product-register.py
│   │       │   └── utils.py
│   │       ├── product-search/       # 商品検索Lambda
│   │       │   ├── product-search.py
│   │       │   └── utils.py
│   │       └── product-list/         # 商品一覧Lambda
│   │           ├── product-list.py
│   │           └── utils.py
│   └── frontend/web/src/
│       └── components/
│           └── productSearch/        # 新規: 商品検索UI
│               ├── ProductSearchMain.jsx
│               ├── ProductRegister.jsx
│               ├── ProductSearchResults.jsx
│               └── BackendComparison.jsx  # Phase 2
│
├── deployment/
│   └── product_service/              # 新規: CDKスタック
│       ├── product_service_stack.py
│       └── constant.py
│
└── docs/
    └── implementation-plan.md        # 本ドキュメント
```

---

## 8. 技術的考慮事項

### Embedding 生成の注意点

- Nova Multimodal Embeddings は **テキストと画像を別リクエスト** で処理する必要がある
- インデックス登録時: `embeddingPurpose: "GENERIC_INDEX"`
- 検索クエリ時: `embeddingPurpose: "GENERIC_RETRIEVAL"`
- 同一ベクトル空間にマッピングされるため、テキストクエリで画像を検索可能

### 大量データ登録（5万件）

- Lambda の15分タイムアウトを考慮し、Step Functions or SQS バッチ処理を検討
- 初期実装: S3イベント → SQS → Lambda（1商品ずつ処理）
- Embedding API のスロットリング対策: 指数バックオフ + 並列度制御

### 検索精度の比較指標

| 指標 | 説明 |
|---|---|
| レイテンシー | API応答時間（ms） |
| Top-K 一致率 | 同一クエリで両バックエンドの上位K件の重複率 |
| 主観評価 | 検索結果の「それっぽさ」を手動評価 |
| コスト | 月額コスト比較 |

---

## 9. コスト見積もり

### 構成A（5万件）

| サービス | 月額見積もり |
|---|---|
| S3 Vectors（2インデックス × 5万ベクトル） | ~$5-10 |
| DynamoDB（5万レコード、オンデマンド） | ~$5-10 |
| Lambda（検索 + 登録） | ~$1-5 |
| Bedrock Nova Embeddings（初期登録10万回 + 検索） | ~$10-20 |
| **合計** | **~$20-45/月** |

### 構成B 追加時

| サービス | 月額追加見積もり |
|---|---|
| OpenSearch Serverless（2 OCU最小） | ~$100-200 |
| **合計（A+B）** | **~$120-245/月** |

---

## 10. 実装の進め方

1. **本プランのレビュー・承認**
2. **Phase 1 実装**（構成A）
   - CDK インフラ → Lambda バックエンド → フロントエンド の順
   - サンプルデータで動作確認
3. **Phase 2 実装**（構成B追加）
   - OpenSearch Serverless 追加
   - 比較UI実装
4. **精度検証**
   - 実データ投入
   - 両構成の検索品質比較
   - 最終構成の判断
