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
            description="User feedback on predictions"
        )
        
        # POST /feedback
        feedback_resource = api.root.add_resource("feedback")
        feedback_resource.add_method(
            "POST",
            apigw.LambdaIntegration(self.feedback_lambda)
        )
        
        self.api_url = api.url