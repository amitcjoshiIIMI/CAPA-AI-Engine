from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as lambda_,
    aws_ecr_assets as ecr_assets,
    aws_apigateway as apigw,  # ADD
    CfnOutput,  # ADD
)
from constructs import Construct

class CapaInferenceStack(Stack):
    def __init__(self, scope: Construct, id: str, storage_stack, auth_stack=None, **kwargs):
        super().__init__(scope, id, **kwargs)

        # Existing Lambda function code...
        self.inference_function = lambda_.DockerImageFunction(
            self, "InferenceFunc",
            code=lambda_.DockerImageCode.from_image_asset(
                directory="lambda/inference",
                platform=ecr_assets.Platform.LINUX_AMD64,
                cmd=["handler.handler"]
            ),
            timeout=Duration.minutes(5),
            memory_size=3008,
            architecture=lambda_.Architecture.X86_64,
            environment={
                "MODEL_BUCKET": storage_stack.model_bucket.bucket_name,
                "DATA_TABLE": storage_stack.data_table.table_name,
                "IMAGES_BUCKET": storage_stack.images_bucket.bucket_name,
                "TRAINING_BUCKET": storage_stack.training_bucket.bucket_name,
            }
        )

        # Grant permissions...
        storage_stack.model_bucket.grant_read(self.inference_function)
        storage_stack.data_table.grant_read_write_data(self.inference_function)
        storage_stack.images_bucket.grant_write(self.inference_function)
        storage_stack.training_bucket.grant_write(self.inference_function)

        # ✨ ADD API GATEWAY
        api = apigw.RestApi(
            self, "InferenceApi",
            rest_api_name="CAPA Inference API",
            description="Defect detection inference endpoint",
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=["Content-Type", "Authorization"]
            )
        )

        # Create Cognito authorizer if auth_stack is provided
        authorizer = None
        if auth_stack:
            authorizer = apigw.CognitoUserPoolsAuthorizer(
                self, "InferenceAuthorizer",
                cognito_user_pools=[auth_stack.user_pool]
            )

        # Connect Lambda to API Gateway
        inference_integration = apigw.LambdaIntegration(
            self.inference_function,
            proxy=True
        )

        # Add method with optional authorization
        api.root.add_method(
            "POST",
            inference_integration,
            authorizer=authorizer,
            authorization_type=apigw.AuthorizationType.COGNITO if authorizer else None
        )

        # Add CORS headers to Gateway Responses so auth errors (4XX) are not blocked by browser
        api.add_gateway_response(
            "Default4XX",
            type=apigw.ResponseType.DEFAULT_4_XX,
            response_headers={
                "Access-Control-Allow-Origin": "'*'",
                "Access-Control-Allow-Headers": "'Content-Type,Authorization'",
                "Access-Control-Allow-Methods": "'OPTIONS,POST'",
            },
        )
        api.add_gateway_response(
            "Default5XX",
            type=apigw.ResponseType.DEFAULT_5_XX,
            response_headers={
                "Access-Control-Allow-Origin": "'*'",
                "Access-Control-Allow-Headers": "'Content-Type,Authorization'",
                "Access-Control-Allow-Methods": "'OPTIONS,POST'",
            },
        )

        # ✨ ADD OUTPUT (matching the script's query)
        CfnOutput(
            self, "InferenceUrl",
            value=api.url,
            description="Inference API endpoint URL",
            export_name="CapaInferenceApiUrl"
        )
