from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
    aws_iam as iam,
    aws_ecr as ecr,
)
from constructs import Construct


class RetrainingStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, storage_stack, **kwargs):
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
        
        # Grant access to golden dataset bucket
        self.sagemaker_role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject", "s3:ListBucket"],
                resources=[
                    "arn:aws:s3:::capa-demo-virginia-acj",
                    "arn:aws:s3:::capa-demo-virginia-acj/*"
                ]
            )
        )
        
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
            timeout=Duration.seconds(60),
            memory_size=256,
            environment={
                "TRAINING_BUCKET": storage_stack.training_bucket.bucket_name,
                "GOLDEN_BUCKET": "capa-demo-virginia-acj",
                "SAGEMAKER_ROLE_ARN": self.sagemaker_role.role_arn,
                "TRAINING_IMAGE_URI": f"{self.training_image_repo.repository_uri}:latest"
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
        
        # API Gateway
        api = apigw.RestApi(
            self, "RetrainingApi",
            rest_api_name="CAPA Retraining API",
            description="Trigger model retraining jobs"
        )
        
        # POST /trigger-retraining
        trigger_resource = api.root.add_resource("trigger-retraining")
        trigger_resource.add_method(
            "POST",
            apigw.LambdaIntegration(self.trigger_lambda)
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

def handler(event, context):
    try:
        response = sagemaker.list_training_jobs(
            SortBy='CreationTime',
            SortOrder='Descending',
            MaxResults=10,
            NameContains='capa-retrain'
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
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'jobs': jobs}, default=str)
        }
    except Exception as e:
        return {
            'statusCode': 500,
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
            apigw.LambdaIntegration(jobs_lambda)
        )
        
        self.api_url = api.url