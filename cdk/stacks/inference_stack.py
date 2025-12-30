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
    def __init__(self, scope: Construct, id: str, storage_stack, **kwargs):
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
            }
        )

        # Grant permissions...
        storage_stack.model_bucket.grant_read(self.inference_function)
        storage_stack.data_table.grant_read_write_data(self.inference_function)

        # ✨ ADD API GATEWAY
        api = apigw.RestApi(
            self, "InferenceApi",
            rest_api_name="CAPA Inference API",
            description="Defect detection inference endpoint",
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
            )
        )

        # Connect Lambda to API Gateway
        inference_integration = apigw.LambdaIntegration(
            self.inference_function,
            proxy=True
        )
        
        api.root.add_method("POST", inference_integration)

        # ✨ ADD OUTPUT (matching the script's query)
        CfnOutput(
            self, "InferenceUrl",
            value=api.url,
            description="Inference API endpoint URL",
            export_name="CapaInferenceApiUrl"
        )
