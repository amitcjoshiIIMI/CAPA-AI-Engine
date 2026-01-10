from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
)
from constructs import Construct


class ReportsCrudStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, storage_stack, **kwargs):
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
        storage_stack.reports_table.grant_read_data(self.reports_lambda)
        storage_stack.reports_bucket.grant_read(self.reports_lambda)

        # API Gateway
        api = apigw.RestApi(
            self, "ReportsCrudApi",
            rest_api_name="CAPA Reports API",
            description="CRUD operations for CAPA reports",
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
            )
        )

        # GET /reports - List all reports
        reports_resource = api.root.add_resource("reports")
        reports_resource.add_method(
            "GET",
            apigw.LambdaIntegration(self.reports_lambda)
        )

        # GET /reports/{report_id} - Get specific report
        report_resource = reports_resource.add_resource("{report_id}")
        report_resource.add_method(
            "GET",
            apigw.LambdaIntegration(self.reports_lambda)
        )

        self.api_url = api.url
