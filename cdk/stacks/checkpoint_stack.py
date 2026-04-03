from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
    aws_iam as iam,
)
from constructs import Construct


class CheckpointStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        storage_stack,
        auth_stack=None,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Lambda function for checkpoint management
        self.checkpoint_lambda = _lambda.Function(
            self,
            "CheckpointManagementFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=_lambda.Code.from_asset("lambda/checkpoint_management"),
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                "CHECKPOINTS_TABLE": storage_stack.checkpoints_table.table_name,
                "MODEL_BUCKET": storage_stack.model_bucket.bucket_name,
            },
        )

        # Grant DynamoDB permissions
        storage_stack.checkpoints_table.grant_read_write_data(self.checkpoint_lambda)

        # Grant S3 permissions for model bucket
        storage_stack.model_bucket.grant_read_write(self.checkpoint_lambda)

        # Additional S3 permissions for listing and copying
        self.checkpoint_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:ListBucket",
                    "s3:ListBucketVersions",
                ],
                resources=[storage_stack.model_bucket.bucket_arn]
            )
        )

        # API Gateway
        self.api = apigw.RestApi(
            self,
            "CheckpointManagementApi",
            rest_api_name="CAPA Checkpoint Management API",
            description="Manage model checkpoints and active model selection",
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=["Content-Type", "Authorization"],
            ),
        )

        # Create Cognito authorizer if auth_stack is provided
        authorizer = None
        if auth_stack:
            authorizer = apigw.CognitoUserPoolsAuthorizer(
                self, "CheckpointAuthorizer",
                cognito_user_pools=[auth_stack.user_pool]
            )

        # Lambda integration
        integration = apigw.LambdaIntegration(self.checkpoint_lambda)

        # Routes
        checkpoints_resource = self.api.root.add_resource("checkpoints")

        # GET /checkpoints - List all checkpoints
        checkpoints_resource.add_method(
            "GET",
            integration,
            authorizer=authorizer,
            authorization_type=apigw.AuthorizationType.COGNITO if authorizer else None
        )

        # GET /checkpoints/active - Get active checkpoint
        active_resource = checkpoints_resource.add_resource("active")
        active_resource.add_method(
            "GET",
            integration,
            authorizer=authorizer,
            authorization_type=apigw.AuthorizationType.COGNITO if authorizer else None
        )

        # POST /checkpoints/active - Set active checkpoint
        active_resource.add_method(
            "POST",
            integration,
            authorizer=authorizer,
            authorization_type=apigw.AuthorizationType.COGNITO if authorizer else None
        )

        # GET /checkpoints/lineage - Get lineage graph data
        lineage_resource = checkpoints_resource.add_resource("lineage")
        lineage_resource.add_method(
            "GET",
            integration,
            authorizer=authorizer,
            authorization_type=apigw.AuthorizationType.COGNITO if authorizer else None
        )

        # GET /checkpoints/{name} - Get specific checkpoint
        checkpoint_name_resource = checkpoints_resource.add_resource("{name}")
        checkpoint_name_resource.add_method(
            "GET",
            integration,
            authorizer=authorizer,
            authorization_type=apigw.AuthorizationType.COGNITO if authorizer else None
        )

        # DELETE /checkpoints/{name} - Delete checkpoint
        checkpoint_name_resource.add_method(
            "DELETE",
            integration,
            authorizer=authorizer,
            authorization_type=apigw.AuthorizationType.COGNITO if authorizer else None
        )

        # Add CORS headers to Gateway Responses so auth errors are not blocked by browser
        self.api.add_gateway_response(
            "Default4XX",
            type=apigw.ResponseType.DEFAULT_4_XX,
            response_headers={
                "Access-Control-Allow-Origin": "'*'",
                "Access-Control-Allow-Headers": "'Content-Type,Authorization'",
            },
        )

        self.api_url = self.api.url
