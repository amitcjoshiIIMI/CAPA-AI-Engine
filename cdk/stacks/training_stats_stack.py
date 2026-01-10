from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
)
from constructs import Construct


class TrainingStatsStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, storage_stack, **kwargs):
        super().__init__(scope, construct_id, **kwargs)
        
        # Lambda function for training stats
        self.training_stats_lambda = _lambda.Function(
            self, "TrainingStatsFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=_lambda.Code.from_asset("lambda/training_stats"),
            timeout=Duration.seconds(60),  # May take time to count large buckets
            memory_size=512,
            environment={
                "TRAINING_BUCKET": storage_stack.training_bucket.bucket_name,
                "GOLDEN_BUCKET": "capa-demo-virginia-acj",  # Your golden dataset bucket
                "CLASS_REGISTRY_TABLE": storage_stack.class_registry_table.table_name,
            }
        )
        
        # Grant permissions
        storage_stack.training_bucket.grant_read(self.training_stats_lambda)
        storage_stack.class_registry_table.grant_read_data(self.training_stats_lambda)
        
        # Grant read access to golden dataset bucket
        # Note: This assumes the golden bucket allows cross-account read or is in same account
        from aws_cdk import aws_iam as iam
        self.training_stats_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:ListBucket", "s3:GetObject"],
                resources=[
                    "arn:aws:s3:::capa-demo-virginia-acj",
                    "arn:aws:s3:::capa-demo-virginia-acj/*"
                ]
            )
        )
        
        # API Gateway
        api = apigw.RestApi(
            self, "TrainingStatsApi",
            rest_api_name="CAPA Training Stats API",
            description="Training data statistics across all buckets"
        )
        
        # GET /training-stats
        stats_resource = api.root.add_resource("training-stats")
        stats_resource.add_method(
            "GET",
            apigw.LambdaIntegration(self.training_stats_lambda)
        )
        
        self.api_url = api.url