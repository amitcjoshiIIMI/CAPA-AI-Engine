from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
)
from constructs import Construct


class TrainingStatsStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, storage_stack, auth_stack=None, **kwargs):
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
                "CLASS_REGISTRY_TABLE": storage_stack.class_registry_table.table_name,
            }
        )
        
        # Grant permissions
        storage_stack.training_bucket.grant_read(self.training_stats_lambda)
        storage_stack.class_registry_table.grant_read_data(self.training_stats_lambda)
        
        # API Gateway
        api = apigw.RestApi(
            self, "TrainingStatsApi",
            rest_api_name="CAPA Training Stats API",
            description="Training data statistics across all buckets",
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=["Content-Type", "Authorization"]
            )
        )

        # Create Cognito authorizer if auth_stack is provided (Expert only endpoint)
        authorizer = None
        if auth_stack:
            authorizer = apigw.CognitoUserPoolsAuthorizer(
                self, "TrainingStatsAuthorizer",
                cognito_user_pools=[auth_stack.user_pool]
            )

        # GET /training-stats
        stats_resource = api.root.add_resource("training-stats")
        stats_resource.add_method(
            "GET",
            apigw.LambdaIntegration(self.training_stats_lambda),
            authorizer=authorizer,
            authorization_type=apigw.AuthorizationType.COGNITO if authorizer else None
        )

        # Add CORS headers to Gateway Responses so auth errors are not blocked by browser
        api.add_gateway_response(
            "Default4XX",
            type=apigw.ResponseType.DEFAULT_4_XX,
            response_headers={
                "Access-Control-Allow-Origin": "'*'",
                "Access-Control-Allow-Headers": "'Content-Type,Authorization'",
            },
        )

        self.api_url = api.url