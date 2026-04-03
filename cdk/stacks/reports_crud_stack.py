from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
)
from constructs import Construct


class ReportsCrudStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, storage_stack, auth_stack=None, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # Lambda function for reports CRUD
        self.reports_lambda = _lambda.Function(
            self, "ReportsCrudFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=_lambda.Code.from_asset("lambda/reports_crud"),
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                "REPORTS_TABLE": storage_stack.reports_table.table_name,
                "REPORTS_BUCKET": storage_stack.reports_bucket.bucket_name,
            }
        )

        # Grant permissions
        storage_stack.reports_table.grant_read_write_data(self.reports_lambda)
        storage_stack.reports_bucket.grant_read_write(self.reports_lambda)

        # API Gateway
        api = apigw.RestApi(
            self, "ReportsCrudApi",
            rest_api_name="CAPA Reports API",
            description="CRUD operations for CAPA reports",
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
                self, "ReportsAuthorizer",
                cognito_user_pools=[auth_stack.user_pool]
            )

        # GET /reports - List all reports
        reports_resource = api.root.add_resource("reports")
        reports_resource.add_method(
            "GET",
            apigw.LambdaIntegration(self.reports_lambda),
            authorizer=authorizer,
            authorization_type=apigw.AuthorizationType.COGNITO if authorizer else None
        )

        # GET /reports/{report_id} - Get specific report
        report_resource = reports_resource.add_resource("{report_id}")
        report_resource.add_method(
            "GET",
            apigw.LambdaIntegration(self.reports_lambda),
            authorizer=authorizer,
            authorization_type=apigw.AuthorizationType.COGNITO if authorizer else None
        )

        # PUT /reports/{report_id} - Update report fields
        report_resource.add_method(
            "PUT",
            apigw.LambdaIntegration(self.reports_lambda),
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
