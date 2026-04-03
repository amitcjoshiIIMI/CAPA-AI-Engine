from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
)
from constructs import Construct


class ImagesStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, storage_stack, auth_stack=None, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # Lambda function for images
        self.images_lambda = _lambda.Function(
            self, "ImagesFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=_lambda.Code.from_asset("lambda/images"),
            timeout=Duration.seconds(60),  # Longer timeout for image uploads
            memory_size=512,  # More memory for image processing
            environment={
                "IMAGES_BUCKET": storage_stack.images_bucket.bucket_name,
            }
        )

        # Grant read/write permissions to images bucket
        storage_stack.images_bucket.grant_read_write(self.images_lambda)

        # API Gateway
        api = apigw.RestApi(
            self, "ImagesApi",
            rest_api_name="CAPA Images API",
            description="Image upload and retrieval for CAPA system",
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
                self, "ImagesAuthorizer",
                cognito_user_pools=[auth_stack.user_pool]
            )

        # /images resource
        images_resource = api.root.add_resource("images")

        # GET /images - List all images
        images_resource.add_method(
            "GET",
            apigw.LambdaIntegration(self.images_lambda),
            authorizer=authorizer,
            authorization_type=apigw.AuthorizationType.COGNITO if authorizer else None
        )

        # POST /images/upload - Upload new image
        upload_resource = images_resource.add_resource("upload")
        upload_resource.add_method(
            "POST",
            apigw.LambdaIntegration(self.images_lambda),
            authorizer=authorizer,
            authorization_type=apigw.AuthorizationType.COGNITO if authorizer else None
        )

        # GET /images/{image_id} - Get specific image (presigned URL)
        image_resource = images_resource.add_resource("{image_id}")
        image_resource.add_method(
            "GET",
            apigw.LambdaIntegration(self.images_lambda),
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
