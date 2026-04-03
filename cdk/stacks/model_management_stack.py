from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
    aws_s3 as s3,
    aws_iam as iam,
)
from constructs import Construct


class ModelManagementStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        model_bucket: s3.IBucket,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Lambda function for model management
        self.model_management_function = _lambda.Function(
            self,
            "ModelManagementFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=_lambda.Code.from_asset("lambda/model_management"),
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                "MODEL_BUCKET": model_bucket.bucket_name,
            },
        )

        # Grant S3 permissions for model bucket (including versioning operations)
        model_bucket.grant_read_write(self.model_management_function)

        # Additional permissions for version operations
        self.model_management_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:ListBucketVersions",
                    "s3:GetObjectVersion",
                    "s3:DeleteObjectVersion",
                ],
                resources=[
                    model_bucket.bucket_arn,
                    f"{model_bucket.bucket_arn}/*"
                ]
            )
        )

        # API Gateway
        self.api = apigw.RestApi(
            self,
            "ModelManagementApi",
            rest_api_name="CAPA Model Management API",
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=["Content-Type", "Authorization"],
            ),
        )

        # Lambda integration
        integration = apigw.LambdaIntegration(self.model_management_function)

        # Routes
        models_resource = self.api.root.add_resource("models")
        models_resource.add_method("GET", integration)  # List all models

        current_resource = models_resource.add_resource("current")
        current_resource.add_method("GET", integration)  # Get current model

        version_resource = models_resource.add_resource("{version_id}")
        version_resource.add_method("DELETE", integration)  # Delete model version

        rollback_resource = version_resource.add_resource("rollback")
        rollback_resource.add_method("POST", integration)  # Rollback to version
