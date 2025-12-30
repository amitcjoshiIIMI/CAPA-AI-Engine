from aws_cdk import (
    Stack,
    RemovalPolicy,
    aws_s3 as s3,
    aws_dynamodb as dynamodb,
    Duration,
)
from constructs import Construct

class StorageStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # S3 Bucket for ML Model Artifacts
        self.model_bucket = s3.Bucket(
            self, "ModelBucket",
            bucket_name=f"capa-model-artifacts-{self.account}",
            versioned=True,  # Track model versions
            removal_policy=RemovalPolicy.RETAIN,  # Don't delete on stack destroy
            auto_delete_objects=False,
        )

        # S3 Bucket for Uploaded Images
        self.images_bucket = s3.Bucket(
            self, "ImagesBucket",
            bucket_name=f"capa-uploaded-images-{self.account}",
            lifecycle_rules=[
                s3.LifecycleRule(
                    enabled=True,
                    expiration=Duration.days(90)  # Auto-cleanup old images
                )
            ],
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # S3 Bucket for Golden Dataset (Retraining)
        self.golden_dataset_bucket = s3.Bucket(
            self, "GoldenDatasetBucket",
            bucket_name=f"capa-golden-dataset-{self.account}",
            versioned=True,
            removal_policy=RemovalPolicy.RETAIN,
            auto_delete_objects=False,
        )

        # S3 Bucket for GroundTruth.json & RAG Documents
        self.rag_bucket = s3.Bucket(
            self, "RagBucket",
            bucket_name=f"capa-rag-documents-{self.account}",
            removal_policy=RemovalPolicy.RETAIN,
            auto_delete_objects=False,
        )

        # S3 Bucket for Generated Reports
        self.reports_bucket = s3.Bucket(
            self, "ReportsBucket",
            bucket_name=f"capa-reports-{self.account}",
            lifecycle_rules=[
                s3.LifecycleRule(
                    enabled=True,
                    expiration=Duration.days(365)
                )
            ],
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # DynamoDB Table for Predictions & Feedback
        self.predictions_table = dynamodb.Table(
            self, "PredictionsTable",
            table_name="capa-predictions",
            partition_key=dynamodb.Attribute(
                name="prediction_id",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp",
                type=dynamodb.AttributeType.NUMBER
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,  # Free-tier friendly
            removal_policy=RemovalPolicy.DESTROY,
            point_in_time_recovery=False,  # Disable to save costs
        )

        # Global Secondary Index for querying by user feedback status
        self.predictions_table.add_global_secondary_index(
            index_name="feedback-status-index",
            partition_key=dynamodb.Attribute(
                name="feedback_status",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp",
                type=dynamodb.AttributeType.NUMBER
            ),
        )

        # Output bucket names (for other stacks)
        self.model_bucket_name = self.model_bucket.bucket_name
        self.images_bucket_name = self.images_bucket.bucket_name
        self.golden_dataset_bucket_name = self.golden_dataset_bucket.bucket_name
        self.rag_bucket_name = self.rag_bucket.bucket_name
        self.reports_bucket_name = self.reports_bucket.bucket_name
