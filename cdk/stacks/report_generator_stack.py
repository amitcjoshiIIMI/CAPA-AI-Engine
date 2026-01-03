from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
    aws_iam as iam,
)
from constructs import Construct


class ReportGeneratorStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, storage_stack, **kwargs):
        super().__init__(scope, construct_id, **kwargs)
        
        # Lambda function for report generation
        self.report_lambda = _lambda.Function(
            self, "ReportGeneratorFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=_lambda.Code.from_asset("lambda/report_generator"),
            timeout=Duration.seconds(60),
            memory_size=512,
        )
        
        # Grant permissions
        storage_stack.reports_table.grant_read_write_data(self.report_lambda)
        storage_stack.reports_bucket.grant_read_write(self.report_lambda)
        
        # Grant Bedrock access
        self.report_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=[
                    "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-5-sonnet-20240620-v1:0"
                ]
            )
        )
        
        # API Gateway
        api = apigw.RestApi(
            self, "ReportGeneratorApi",
            rest_api_name="CAPA Report Generator",
            description="Generate CAPA reports using LLM"
        )
        
        # POST /generate-report
        generate_resource = api.root.add_resource("generate-report")
        generate_resource.add_method(
            "POST",
            apigw.LambdaIntegration(self.report_lambda)
        )
        
        self.api_url = api.url