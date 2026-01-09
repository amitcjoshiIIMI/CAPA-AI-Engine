from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
)
from constructs import Construct


class ExpertApproveStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, storage_stack, **kwargs):
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
            }
        )
        
        # Grant permissions
        storage_stack.feedback_table.grant_read_write_data(self.expert_approve_lambda)
        storage_stack.images_bucket.grant_read(self.expert_approve_lambda)
        storage_stack.training_bucket.grant_write(self.expert_approve_lambda)
        
        # API Gateway
        api = apigw.RestApi(
            self, "ExpertApproveApi",
            rest_api_name="CAPA Expert Approve API",
            description="Expert approval of feedback items"
        )
        
        # POST /expert-approve
        approve_resource = api.root.add_resource("expert-approve")
        approve_resource.add_method(
            "POST",
            apigw.LambdaIntegration(self.expert_approve_lambda)
        )
        
        self.api_url = api.url