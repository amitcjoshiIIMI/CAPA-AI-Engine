from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
)
from constructs import Construct


class ExpertReviewStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, storage_stack, **kwargs):
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
            description="Expert review queue for predictions"
        )
        
        # GET /expert-review
        review_resource = api.root.add_resource("expert-review")
        review_resource.add_method(
            "GET",
            apigw.LambdaIntegration(self.expert_review_lambda)
        )
        
        self.api_url = api.url