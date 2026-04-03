from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
)
from constructs import Construct


class ExpertReviewStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, storage_stack, auth_stack=None, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # Lambda function for expert review queue
        self.expert_review_lambda = _lambda.Function(
            self, "ExpertReviewFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=_lambda.Code.from_asset("lambda/expert_review"),
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                "FEEDBACK_TABLE": storage_stack.feedback_table.table_name,
            }
        )

        # Grant permissions
        storage_stack.feedback_table.grant_read_data(self.expert_review_lambda)

        # API Gateway
        api = apigw.RestApi(
            self, "ExpertReviewApi",
            rest_api_name="CAPA Expert Review API",
            description="Expert review queue for predictions",
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
                self, "ExpertReviewAuthorizer",
                cognito_user_pools=[auth_stack.user_pool]
            )

        # GET /expert-review
        review_resource = api.root.add_resource("expert-review")
        review_resource.add_method(
            "GET",
            apigw.LambdaIntegration(self.expert_review_lambda),
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