# Product Service Stack Constants
LAMBDA_NAME_PREFIX = 'nova-mme-'
API_NAME_PREFIX = 'nova-mme-product'

DYNAMO_PRODUCT_TABLE = "nova_mme_product_master"

S3_VECTOR_BUCKET_NAME = "nova-mme-vector-bucket"
S3_VECTOR_INDEX_PRODUCT_IMAGE = "product-image-vectors"
S3_VECTOR_INDEX_PRODUCT_TEXT = "product-text-vectors"
EMBEDDING_DIM = "1024"

MODEL_ID_BEDROCK_MME = "amazon.nova-2-multimodal-embeddings-v1:0"

S3_PRE_SIGNED_URL_EXPIRY_S = "3600"
LAMBDA_LAYER_SOURCE_S3_KEY_BOTO3 = "layer/boto3_layer.zip"
