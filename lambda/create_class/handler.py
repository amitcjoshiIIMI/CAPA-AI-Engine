import json
import boto3
import os
from datetime import datetime
from decimal import Decimal

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
s3 = boto3.client('s3', region_name='us-east-1')

CLASS_REGISTRY_TABLE = os.environ['CLASS_REGISTRY_TABLE']
TRAINING_BUCKET = os.environ['TRAINING_BUCKET']


def lambda_handler(event, context):
    """
    POST /create-class
    Input:
    {
        "class_name": "Class_7",
        "description": "New defect type - delamination"
    }
    
    Actions:
    - Validate class doesn't already exist
    - Create entry in class registry
    - Create S3 folders in training bucket
    """
    try:
        body = json.loads(event['body']) if 'body' in event else event
        
        class_name = body['class_name'].strip()
        description = body.get('description', '').strip()
        
        # Validation
        if not class_name:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'class_name is required'})
            }
        
        # Check if class already exists
        table = dynamodb.Table(CLASS_REGISTRY_TABLE)
        existing = table.get_item(Key={'class_name': class_name})
        
        if 'Item' in existing:
            return {
                'statusCode': 409,
                'body': json.dumps({
                    'error': f'Class "{class_name}" already exists',
                    'existing_class': existing['Item']
                })
            }
        
        # Create class entry
        class_record = {
            'class_name': class_name,
            'description': description,
            'created_at': datetime.now().isoformat(),
            'is_original': False,
            'image_count': 0
        }
        
        table.put_item(Item=class_record)
        
        # Create S3 folders
        readme_content = f"Training data for {class_name}\nCreated: {class_record['created_at']}\n"
        
        folders = [
            f"pending/{class_name}/.readme",
            f"approved/train/{class_name}/.readme"
        ]
        
        for folder in folders:
            s3.put_object(
                Bucket=TRAINING_BUCKET,
                Key=folder,
                Body=readme_content.encode('utf-8')
            )
        
        return {
            'statusCode': 201,
            'body': json.dumps({
                'message': 'Class created successfully',
                'class': class_record,
                's3_folders': [f"s3://{TRAINING_BUCKET}/{f}" for f in folders]
            })
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }