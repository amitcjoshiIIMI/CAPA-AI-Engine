import json
import boto3
import os
from datetime import datetime

sagemaker = boto3.client('sagemaker', region_name='us-east-1')
s3 = boto3.client('s3', region_name='us-east-1')

TRAINING_BUCKET = os.environ['TRAINING_BUCKET']
GOLDEN_BUCKET = os.environ['GOLDEN_BUCKET']
ROLE_ARN = os.environ['SAGEMAKER_ROLE_ARN']
IMAGE_URI = os.environ.get('TRAINING_IMAGE_URI', 'pytorch-training-image')  # Will update later


def lambda_handler(event, context):
    """
    POST /trigger-retraining
    Input (optional):
    {
        "epochs": 10,
        "batch_size": 32,
        "learning_rate": 0.001,
        "reason": "Manual trigger by expert"
    }
    
    Triggers SageMaker training job
    """
    try:
        body = json.loads(event['body']) if 'body' in event else event
        
        epochs = body.get('epochs', 10)
        batch_size = body.get('batch_size', 32)
        learning_rate = body.get('learning_rate', 0.001)
        reason = body.get('reason', 'API trigger')
        
        # Create unique job name
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        job_name = f"capa-retrain-{timestamp}"
        
        # Training job configuration
        training_config = {
            'TrainingJobName': job_name,
            'RoleArn': ROLE_ARN,
            'AlgorithmSpecification': {
                'TrainingImage': IMAGE_URI,
                'TrainingInputMode': 'File'
            },
            'InputDataConfig': [
                {
                    'ChannelName': 'train',
                    'DataSource': {
                        'S3DataSource': {
                            'S3DataType': 'S3Prefix',
                            'S3Uri': f's3://{TRAINING_BUCKET}/approved/train/',
                            'S3DataDistributionType': 'FullyReplicated'
                        }
                    }
                },
                {
                    'ChannelName': 'test',
                    'DataSource': {
                        'S3DataSource': {
                            'S3DataType': 'S3Prefix',
                            'S3Uri': f's3://{GOLDEN_BUCKET}/NEU Metal Surface Defects Data/test/',
                            'S3DataDistributionType': 'FullyReplicated'
                        }
                    }
                }
            ],
            'OutputDataConfig': {
                'S3OutputPath': f's3://{TRAINING_BUCKET}/models/'
            },
            'ResourceConfig': {
                'InstanceType': 'ml.m5.xlarge',
                'InstanceCount': 1,
                'VolumeSizeInGB': 30
            },
            'StoppingCondition': {
                'MaxRuntimeInSeconds': 3600  # 1 hour max
            },
            'HyperParameters': {
                'epochs': str(epochs),
                'batch_size': str(batch_size),  # Changed from 'batch-size'
                'learning_rate': str(learning_rate)  # Changed from 'learning-rate'
            }
        }
        
        # Start training job
        response = sagemaker.create_training_job(**training_config)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Training job started',
                'job_name': job_name,
                'reason': reason,
                'config': {
                    'epochs': epochs,
                    'batch_size': batch_size,
                    'learning_rate': learning_rate
                },
                'status_url': f'https://console.aws.amazon.com/sagemaker/home?region=us-east-1#/jobs/{job_name}'
            })
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }