from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
)
from constructs import Construct


class CreateClassStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, storage_stack, **kwargs):
        super().__init__(scope, construct_id, **kwargs)
        
        # Lambda function for class creation
        self.create_class_lambda = _lambda.Function(
            self, "CreateClassFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=_lambda.Code.from_asset("lambda/create_class"),
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                "CLASS_REGISTRY_TABLE": storage_stack.class_registry_table.table_name,
                "TRAINING_BUCKET": storage_stack.training_bucket.bucket_name,
            }
        )
        
        # Grant permissions
        storage_stack.class_registry_table.grant_read_write_data(self.create_class_lambda)
        storage_stack.training_bucket.grant_write(self.create_class_lambda)
        
        # API Gateway
        api = apigw.RestApi(
            self, "CreateClassApi",
            rest_api_name="CAPA Create Class API",
            description="Create new defect classes dynamically"
        )
        
        # POST /create-class
        create_resource = api.root.add_resource("create-class")
        create_resource.add_method(
            "POST",
            apigw.LambdaIntegration(self.create_class_lambda)
        )
        
        # GET /classes (list all classes)
        classes_resource = api.root.add_resource("classes")
        
        # Simple Lambda inline for listing classes
        list_classes_lambda = _lambda.Function(
            self, "ListClassesFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="index.handler",
            code=_lambda.Code.from_inline(f"""
import json
import boto3
import os

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('{storage_stack.class_registry_table.table_name}')

def handler(event, context):
    try:
        response = table.scan()
        items = response.get('Items', [])
        
        # Sort: original classes first, then by name
        items.sort(key=lambda x: (not x.get('is_original', False), x['class_name']))
        
        return {{
            'statusCode': 200,
            'headers': {{'Content-Type': 'application/json'}},
            'body': json.dumps({{'count': len(items), 'classes': items}}, default=str)
        }}
    except Exception as e:
        return {{
            'statusCode': 500,
            'body': json.dumps({{'error': str(e)}})
        }}
"""),
            timeout=Duration.seconds(10),
            memory_size=128
        )
        
        storage_stack.class_registry_table.grant_read_data(list_classes_lambda)
        
        classes_resource.add_method(
            "GET",
            apigw.LambdaIntegration(list_classes_lambda)
        )
        
        self.api_url = api.url