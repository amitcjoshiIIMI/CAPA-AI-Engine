from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
)
from constructs import Construct


class ExpertApproveStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, storage_stack, auth_stack=None, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # Lambda function for expert approval
        self.expert_approve_lambda = _lambda.Function(
            self, "ExpertApproveFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=_lambda.Code.from_asset("lambda/expert_approve"),
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                "FEEDBACK_TABLE": storage_stack.feedback_table.table_name,
                "IMAGES_BUCKET": storage_stack.images_bucket.bucket_name,
                "TRAINING_BUCKET": storage_stack.training_bucket.bucket_name,
                "REPORTS_TABLE": storage_stack.reports_table.table_name,
                "REPORTS_BUCKET": storage_stack.reports_bucket.bucket_name,
                "CLASS_REGISTRY_TABLE": storage_stack.class_registry_table.table_name,
            }
        )

        # Grant permissions
        storage_stack.feedback_table.grant_read_write_data(self.expert_approve_lambda)
        storage_stack.images_bucket.grant_read(self.expert_approve_lambda)
        storage_stack.training_bucket.grant_read_write(self.expert_approve_lambda)
        storage_stack.reports_table.grant_read_write_data(self.expert_approve_lambda)
        storage_stack.reports_bucket.grant_read_write(self.expert_approve_lambda)
        storage_stack.class_registry_table.grant_read_data(self.expert_approve_lambda)

        # API Gateway
        api = apigw.RestApi(
            self, "ExpertApproveApi",
            rest_api_name="CAPA Expert Approve API",
            description="Expert approval of feedback items",
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
                self, "ExpertApproveAuthorizer",
                cognito_user_pools=[auth_stack.user_pool]
            )

        # POST /expert-approve
        approve_resource = api.root.add_resource("expert-approve")
        approve_resource.add_method(
            "POST",
            apigw.LambdaIntegration(self.expert_approve_lambda),
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