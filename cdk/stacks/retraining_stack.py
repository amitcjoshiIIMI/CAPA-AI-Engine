from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
    aws_iam as iam,
    aws_ecr as ecr,
    aws_events as events,
    aws_events_targets as targets,
)
from constructs import Construct


class RetrainingStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, storage_stack, auth_stack=None, **kwargs):
        super().__init__(scope, construct_id, **kwargs)
        
        # SageMaker execution role
        self.sagemaker_role = iam.Role(
            self, "SageMakerExecutionRole",
            assumed_by=iam.ServicePrincipal("sagemaker.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSageMakerFullAccess")
            ]
        )
        
        # Grant access to buckets
        storage_stack.training_bucket.grant_read_write(self.sagemaker_role)
        storage_stack.model_bucket.grant_read_write(self.sagemaker_role)
        
        # ECR repository for training image
        self.training_image_repo = ecr.Repository(
            self, "TrainingImageRepo",
            repository_name="capa-training",
            removal_policy=RemovalPolicy.DESTROY
        )
        
        # Lambda function to trigger training
        self.trigger_lambda = _lambda.Function(
            self, "TriggerRetrainingFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=_lambda.Code.from_asset("lambda/trigger_retraining"),
            timeout=Duration.seconds(120),
            memory_size=512,
            environment={
                "TRAINING_BUCKET": storage_stack.training_bucket.bucket_name,
                "MODEL_BUCKET": storage_stack.model_bucket.bucket_name,
                "SAGEMAKER_ROLE_ARN": self.sagemaker_role.role_arn,
                "TRAINING_IMAGE_URI": f"{self.training_image_repo.repository_uri}:latest",
                "CHECKPOINTS_TABLE": storage_stack.checkpoints_table.table_name
            }
        )

        # Grant Lambda permission to start SageMaker jobs
        self.trigger_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "sagemaker:CreateTrainingJob",
                    "sagemaker:DescribeTrainingJob",
                    "iam:PassRole"
                ],
                resources=["*"]
            )
        )

        # Grant DynamoDB permissions for checkpoints table
        storage_stack.checkpoints_table.grant_read_write_data(self.trigger_lambda)

        # Grant S3 read permissions for model bucket (to read metadata)
        storage_stack.model_bucket.grant_read(self.trigger_lambda)
        
        # API Gateway
        api = apigw.RestApi(
            self, "RetrainingApi",
            rest_api_name="CAPA Retraining API",
            description="Trigger model retraining jobs",
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
                self, "RetrainingAuthorizer",
                cognito_user_pools=[auth_stack.user_pool]
            )

        # POST /trigger-retraining
        trigger_resource = api.root.add_resource("trigger-retraining")
        trigger_resource.add_method(
            "POST",
            apigw.LambdaIntegration(self.trigger_lambda),
            authorizer=authorizer,
            authorization_type=apigw.AuthorizationType.COGNITO if authorizer else None
        )

        # POST /train-golden - Train the golden model (first time only)
        golden_resource = api.root.add_resource("train-golden")
        golden_resource.add_method(
            "POST",
            apigw.LambdaIntegration(self.trigger_lambda),
            authorizer=authorizer,
            authorization_type=apigw.AuthorizationType.COGNITO if authorizer else None
        )

        # POST /register-checkpoint - Register a completed training job as checkpoint
        register_resource = api.root.add_resource("register-checkpoint")
        register_resource.add_method(
            "POST",
            apigw.LambdaIntegration(self.trigger_lambda),
            authorizer=authorizer,
            authorization_type=apigw.AuthorizationType.COGNITO if authorizer else None
        )
        
        # GET /training-jobs (list recent jobs)
        jobs_lambda = _lambda.Function(
            self, "ListTrainingJobsFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="index.handler",
            code=_lambda.Code.from_inline("""
import json
import boto3

sagemaker = boto3.client('sagemaker', region_name='us-east-1')

CORS_HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*'
}

def handler(event, context):
    try:
        response = sagemaker.list_training_jobs(
            SortBy='CreationTime',
            SortOrder='Descending',
            MaxResults=10,
            NameContains='capa-'
        )

        jobs = []
        for job in response.get('TrainingJobSummaries', []):
            jobs.append({
                'job_name': job['TrainingJobName'],
                'status': job['TrainingJobStatus'],
                'created': job['CreationTime'].isoformat(),
                'duration': str(job.get('TrainingEndTime', job['CreationTime']) - job['CreationTime'])
            })

        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps({'jobs': jobs}, default=str)
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': str(e)})
        }
"""),
            timeout=Duration.seconds(30),
            memory_size=128
        )
        
        jobs_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["sagemaker:ListTrainingJobs", "sagemaker:DescribeTrainingJob"],
                resources=["*"]
            )
        )
        
        jobs_resource = api.root.add_resource("training-jobs")
        jobs_resource.add_method(
            "GET",
            apigw.LambdaIntegration(jobs_lambda),
            authorizer=authorizer,
            authorization_type=apigw.AuthorizationType.COGNITO if authorizer else None
        )

        # GET /training-jobs/{job_name} - Get single job details
        get_job_lambda = _lambda.Function(
            self, "GetTrainingJobFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=_lambda.Code.from_asset("lambda/get_training_job"),
            timeout=Duration.seconds(30),
            memory_size=128
        )

        get_job_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["sagemaker:DescribeTrainingJob"],
                resources=["*"]
            )
        )

        job_name_resource = jobs_resource.add_resource("{job_name}")
        job_name_resource.add_method(
            "GET",
            apigw.LambdaIntegration(get_job_lambda),
            authorizer=authorizer,
            authorization_type=apigw.AuthorizationType.COGNITO if authorizer else None
        )

        # POST /training-jobs/{job_name}/stop - Stop a training job
        stop_job_lambda = _lambda.Function(
            self, "StopTrainingJobFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=_lambda.Code.from_asset("lambda/stop_training_job"),
            timeout=Duration.seconds(30),
            memory_size=128
        )

        stop_job_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["sagemaker:StopTrainingJob", "sagemaker:DescribeTrainingJob"],
                resources=["*"]
            )
        )

        stop_resource = job_name_resource.add_resource("stop")

        # Training Metrics Lambda - fetch metrics from CloudWatch
        self.metrics_lambda = _lambda.Function(
            self, "TrainingMetricsFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=_lambda.Code.from_asset("lambda/training_metrics"),
            timeout=Duration.seconds(30),
            memory_size=256,
        )

        # Grant CloudWatch and SageMaker read permissions
        self.metrics_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "cloudwatch:GetMetricStatistics",
                    "cloudwatch:GetMetricData",
                    "sagemaker:DescribeTrainingJob"
                ],
                resources=["*"]
            )
        )

        # GET /training-jobs/{job_name}/metrics
        metrics_resource = job_name_resource.add_resource("metrics")
        metrics_resource.add_method(
            "GET",
            apigw.LambdaIntegration(self.metrics_lambda),
            authorizer=authorizer,
            authorization_type=apigw.AuthorizationType.COGNITO if authorizer else None
        )

        stop_resource.add_method(
            "POST",
            apigw.LambdaIntegration(stop_job_lambda),
            authorizer=authorizer,
            authorization_type=apigw.AuthorizationType.COGNITO if authorizer else None
        )

        # Auto-register checkpoint Lambda — triggered by EventBridge when SageMaker jobs complete
        auto_register_lambda = _lambda.Function(
            self, "AutoRegisterCheckpointFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=_lambda.Code.from_asset("lambda/auto_register_checkpoint"),
            timeout=Duration.seconds(120),
            memory_size=512,
            environment={
                "MODEL_BUCKET": storage_stack.model_bucket.bucket_name,
                "CHECKPOINTS_TABLE": storage_stack.checkpoints_table.table_name
            }
        )

        # Grant permissions
        storage_stack.checkpoints_table.grant_read_write_data(auto_register_lambda)
        storage_stack.model_bucket.grant_read(auto_register_lambda)
        auto_register_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["sagemaker:DescribeTrainingJob"],
                resources=["*"]
            )
        )

        # EventBridge rule: trigger on SageMaker training job state changes for CAPA jobs
        events.Rule(
            self, "SageMakerJobCompletionRule",
            event_pattern=events.EventPattern(
                source=["aws.sagemaker"],
                detail_type=["SageMaker Training Job State Change"],
                detail={
                    "TrainingJobStatus": ["Completed", "Failed", "Stopped"]
                }
            ),
            targets=[targets.LambdaFunction(auto_register_lambda)]
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