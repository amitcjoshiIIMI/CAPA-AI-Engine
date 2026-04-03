from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
)
from constructs import Construct


class FeedbackStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, storage_stack, auth_stack=None, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # Lambda function for feedback
        self.feedback_lambda = _lambda.Function(
            self, "FeedbackFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=_lambda.Code.from_asset("lambda/feedback"),
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                "FEEDBACK_TABLE": storage_stack.feedback_table.table_name,
            }
        )

        # Grant permissions
        storage_stack.feedback_table.grant_read_write_data(self.feedback_lambda)

        # API Gateway
        api = apigw.RestApi(
            self, "FeedbackApi",
            rest_api_name="CAPA Feedback API",
            description="User feedback on predictions",
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
                self, "FeedbackAuthorizer",
                cognito_user_pools=[auth_stack.user_pool]
            )

        # /feedback resource
        feedback_resource = api.root.add_resource("feedback")

        # POST /feedback - Create new feedback
        feedback_resource.add_method(
            "POST",
            apigw.LambdaIntegration(self.feedback_lambda),
            authorizer=authorizer,
            authorization_type=apigw.AuthorizationType.COGNITO if authorizer else None
        )

        # GET /feedback - List all feedback
        feedback_resource.add_method(
            "GET",
            apigw.LambdaIntegration(self.feedback_lambda),
            authorizer=authorizer,
            authorization_type=apigw.AuthorizationType.COGNITO if authorizer else None
        )

        # /feedback/{image_id} resource
        image_feedback = feedback_resource.add_resource("{image_id}")

        # GET /feedback/{image_id} - List feedback for specific image
        image_feedback.add_method(
            "GET",
            apigw.LambdaIntegration(self.feedback_lambda),
            authorizer=authorizer,
            authorization_type=apigw.AuthorizationType.COGNITO if authorizer else None
        )

        # /feedback/{image_id}/{timestamp} resource
        specific_feedback = image_feedback.add_resource("{timestamp}")

        # GET /feedback/{image_id}/{timestamp} - Get specific feedback
        specific_feedback.add_method(
            "GET",
            apigw.LambdaIntegration(self.feedback_lambda),
            authorizer=authorizer,
            authorization_type=apigw.AuthorizationType.COGNITO if authorizer else None
        )

        # PATCH /feedback/{image_id}/{timestamp} - Mark as reviewed
        specific_feedback.add_method(
            "PATCH",
            apigw.LambdaIntegration(self.feedback_lambda),
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
