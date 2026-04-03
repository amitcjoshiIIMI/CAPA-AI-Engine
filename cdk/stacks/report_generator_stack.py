from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
    aws_iam as iam,
)
from constructs import Construct


class ReportGeneratorStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, storage_stack, auth_stack=None, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # Lambda function for report generation
        self.report_lambda = _lambda.Function(
            self, "ReportGeneratorFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=_lambda.Code.from_asset("lambda/report_generator"),
            timeout=Duration.seconds(60),
            memory_size=512,
            environment={
                "REPORTS_TABLE": storage_stack.reports_table.table_name,
                "REPORTS_BUCKET": storage_stack.reports_bucket.bucket_name,
            }
        )
        
        # Grant permissions
        storage_stack.reports_table.grant_read_write_data(self.report_lambda)
        storage_stack.reports_bucket.grant_read_write(self.report_lambda)
        
        # Grant Bedrock access
        self.report_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=[
                    "arn:aws:bedrock:*:507282033774:inference-profile/us.anthropic.claude-sonnet-4-*",
                    "arn:aws:bedrock:*::foundation-model/anthropic.claude-sonnet-4-*",
                ]
            )
        )
        
        # API Gateway
        api = apigw.RestApi(
            self, "ReportGeneratorApi",
            rest_api_name="CAPA Report Generator",
            description="Generate CAPA reports using LLM",
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
                self, "ReportGeneratorAuthorizer",
                cognito_user_pools=[auth_stack.user_pool]
            )

        # POST /generate-report
        generate_resource = api.root.add_resource("generate-report")
        generate_resource.add_method(
            "POST",
            apigw.LambdaIntegration(self.report_lambda),
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