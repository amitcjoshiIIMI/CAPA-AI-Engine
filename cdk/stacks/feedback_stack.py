from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
)
from constructs import Construct


class FeedbackStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, storage_stack, **kwargs):
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
            )
        )

        # /feedback resource
        feedback_resource = api.root.add_resource("feedback")

        # POST /feedback - Create new feedback
        feedback_resource.add_method(
            "POST",
            apigw.LambdaIntegration(self.feedback_lambda)
        )

        # GET /feedback - List all feedback
        feedback_resource.add_method(
            "GET",
            apigw.LambdaIntegration(self.feedback_lambda)
        )

        # /feedback/{image_id} resource
        image_feedback = feedback_resource.add_resource("{image_id}")

        # GET /feedback/{image_id} - List feedback for specific image
        image_feedback.add_method(
            "GET",
            apigw.LambdaIntegration(self.feedback_lambda)
        )

        # /feedback/{image_id}/{timestamp} resource
        specific_feedback = image_feedback.add_resource("{timestamp}")

        # GET /feedback/{image_id}/{timestamp} - Get specific feedback
        specific_feedback.add_method(
            "GET",
            apigw.LambdaIntegration(self.feedback_lambda)
        )

        # PATCH /feedback/{image_id}/{timestamp} - Mark as reviewed
        specific_feedback.add_method(
            "PATCH",
            apigw.LambdaIntegration(self.feedback_lambda)
        )

        self.api_url = api.url
