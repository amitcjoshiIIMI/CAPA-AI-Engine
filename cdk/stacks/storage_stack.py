from aws_cdk import (
    Stack,
    RemovalPolicy,
    Duration,
    aws_s3 as s3,
    aws_dynamodb as dynamodb,
)
from constructs import Construct

class StorageStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # S3 Bucket for images
        self.images_bucket = s3.Bucket(
            self, "ImagesBucket",
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="DeleteOldImages",
                    expiration=Duration.days(90)
                )
            ],
            cors=[
                s3.CorsRule(
                    allowed_methods=[s3.HttpMethods.GET, s3.HttpMethods.HEAD],
                    allowed_origins=["*"],
                    allowed_headers=["*"],
                    max_age=3000
                )
            ]
        )

        # ✨ ADD: S3 Bucket for ML models
        self.model_bucket = s3.Bucket(
            self, "ModelsBucket",
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )
        # S3 Bucket for CAPA reports
        self.reports_bucket = s3.Bucket(
            self, "ReportsBucket",
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )
        # S3 Bucket for training data
        self.training_bucket = s3.Bucket(
            self, "TrainingBucket",
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )
        # DynamoDB Table for feedback
        self.feedback_table = dynamodb.Table(
            self, "FeedbackTable",
            partition_key=dynamodb.Attribute(
                name="image_id",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
            point_in_time_recovery=True
        )

        # DynamoDB Table for CAPA reports
        self.reports_table = dynamodb.Table(
            self, "ReportsTable",
            partition_key=dynamodb.Attribute(
                name="report_id",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="created_at",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
            point_in_time_recovery=True
        )

        # ✨ ADD: DynamoDB Table for inference results/data
        self.data_table = dynamodb.Table(
            self, "InferenceDataTable",
            partition_key=dynamodb.Attribute(
                name="image_id",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="inference_timestamp",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
            point_in_time_recovery=True
        )
        
        # DynamoDB Table for class registry
        self.class_registry_table = dynamodb.Table(
            self, "ClassRegistryTable",
            partition_key=dynamodb.Attribute(
                name="class_name",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
            point_in_time_recovery=True
        )

        # DynamoDB Table for model checkpoints
        self.checkpoints_table = dynamodb.Table(
            self, "CheckpointsTable",
            partition_key=dynamodb.Attribute(
                name="checkpoint_name",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
            point_in_time_recovery=True
        )

        # GSI for querying checkpoints by parent (for lineage)
        self.checkpoints_table.add_global_secondary_index(
            index_name="ParentIndex",
            partition_key=dynamodb.Attribute(
                name="parent_checkpoint",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="created_at",
                type=dynamodb.AttributeType.STRING
            )
        )

        # GSI for querying active checkpoint
        self.checkpoints_table.add_global_secondary_index(
            index_name="ActiveIndex",
            partition_key=dynamodb.Attribute(
                name="is_active",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="created_at",
                type=dynamodb.AttributeType.STRING
            )
        )
