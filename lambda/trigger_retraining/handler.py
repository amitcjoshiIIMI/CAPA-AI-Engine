import json
import boto3
import os
import tarfile
import shutil
from datetime import datetime
from decimal import Decimal

sagemaker = boto3.client('sagemaker', region_name='us-east-1')
s3 = boto3.client('s3', region_name='us-east-1')
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

TRAINING_BUCKET = os.environ['TRAINING_BUCKET']
MODEL_BUCKET = os.environ['MODEL_BUCKET']
ROLE_ARN = os.environ['SAGEMAKER_ROLE_ARN']
IMAGE_URI = os.environ.get('TRAINING_IMAGE_URI', 'pytorch-training-image')
CHECKPOINTS_TABLE = os.environ.get('CHECKPOINTS_TABLE', '')


def lambda_handler(event, context):
    """
    Unified training handler supporting:
    - POST /trigger-retraining - Start retraining with checkpoint
    - POST /train-golden - Train golden model from golden dataset
    - POST /register-checkpoint/{job_name} - Register completed training as checkpoint
    """
    try:
        http_method = event.get('httpMethod', 'POST')
        path = event.get('path', '')
        body = json.loads(event['body']) if 'body' in event and event['body'] else event
        path_params = event.get('pathParameters') or {}

        if '/train-golden' in path:
            return train_golden_model(body)
        elif '/register-checkpoint' in path:
            job_name = path_params.get('job_name') or body.get('job_name')
            return register_checkpoint(job_name)
        else:
            return trigger_retraining(body)

    except Exception as e:
        print(f"Error: {str(e)}")
        return error_response(500, str(e))


def train_golden_model(body):
    """Train the first model from golden dataset only"""
    checkpoint_name = body.get('checkpoint_name', 'golden_model')
    # Optimized hyperparameters for 95%+ accuracy
    epochs = body.get('epochs', 50)
    batch_size = body.get('batch_size', 32)
    learning_rate = body.get('learning_rate', 0.0001)  # Lower LR for better convergence

    # Check if golden model already exists
    if CHECKPOINTS_TABLE:
        table = dynamodb.Table(CHECKPOINTS_TABLE)
        response = table.get_item(Key={'checkpoint_name': 'golden_model'})
        if 'Item' in response:
            return error_response(400, 'Golden model already exists. Use regular retraining to create new checkpoints.')

    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    job_name = f"capa-golden-{timestamp}"

    # Training job configuration - train and test both from golden dataset
    training_config = {
        'TrainingJobName': job_name,
        'RoleArn': ROLE_ARN,
        'AlgorithmSpecification': {
            'TrainingImage': IMAGE_URI,
            'TrainingInputMode': 'File',
            'MetricDefinitions': [
                {'Name': 'train:loss', 'Regex': r'train_loss=([0-9\\.]+);'},
                {'Name': 'test:accuracy', 'Regex': r'test_accuracy=([0-9\\.]+);'}
            ]
        },
        'InputDataConfig': [
            {
                'ChannelName': 'train',
                'DataSource': {
                    'S3DataSource': {
                        'S3DataType': 'S3Prefix',
                        'S3Uri': f's3://{TRAINING_BUCKET}/golden/train/',
                        'S3DataDistributionType': 'FullyReplicated'
                    }
                }
            },
            {
                'ChannelName': 'test',
                'DataSource': {
                    'S3DataSource': {
                        'S3DataType': 'S3Prefix',
                        'S3Uri': f's3://{TRAINING_BUCKET}/golden/test/',
                        'S3DataDistributionType': 'FullyReplicated'
                    }
                }
            }
        ],
        'OutputDataConfig': {
            'S3OutputPath': f's3://{MODEL_BUCKET}/checkpoints/{checkpoint_name}/'
        },
        'ResourceConfig': {
            'InstanceType': 'ml.m5.xlarge',
            'InstanceCount': 1,
            'VolumeSizeInGB': 30
        },
        'StoppingCondition': {
            'MaxRuntimeInSeconds': 3600
        },
        'HyperParameters': {
            'epochs': str(epochs),
            'batch_size': str(batch_size),
            'learning_rate': str(learning_rate),
            'checkpoint_name': checkpoint_name,
            'parent_checkpoint': '',
            'is_golden': 'true'
        }
    }

    response = sagemaker.create_training_job(**training_config)

    # Create pending checkpoint entry
    if CHECKPOINTS_TABLE:
        table = dynamodb.Table(CHECKPOINTS_TABLE)
        table.put_item(Item={
            'checkpoint_name': checkpoint_name,
            'status': 'training',
            'is_golden': True,
            'is_active': 'false',
            'parent_checkpoint': 'none',  # Use 'none' string since GSI doesn't accept NULL
            'training_job_name': job_name,
            'created_at': datetime.now().isoformat(),
            'epochs': epochs,
            'batch_size': batch_size,
            'learning_rate': Decimal(str(learning_rate)),
            'training_data_source': 'golden_dataset'
        })

    return success_response({
        'message': 'Golden model training started',
        'job_name': job_name,
        'checkpoint_name': checkpoint_name,
        'is_golden': True,
        'config': {
            'epochs': epochs,
            'batch_size': batch_size,
            'learning_rate': learning_rate
        },
        'status_url': f'https://console.aws.amazon.com/sagemaker/home?region=us-east-1#/jobs/{job_name}'
    })


def trigger_retraining(body):
    """Trigger retraining with checkpoint support"""
    checkpoint_name = body.get('checkpoint_name')
    if not checkpoint_name:
        return error_response(400, 'checkpoint_name is required')

    parent_checkpoint = body.get('parent_checkpoint')
    # Optimized hyperparameters for 95%+ accuracy
    epochs = body.get('epochs', 50)
    batch_size = body.get('batch_size', 32)
    learning_rate = body.get('learning_rate', 0.0001)  # Lower LR for better convergence
    reason = body.get('reason', 'API trigger')

    # Validate checkpoint name doesn't already exist
    if CHECKPOINTS_TABLE:
        table = dynamodb.Table(CHECKPOINTS_TABLE)
        response = table.get_item(Key={'checkpoint_name': checkpoint_name})
        if 'Item' in response:
            return error_response(400, f'Checkpoint {checkpoint_name} already exists. Choose a different name.')

        # Validate parent checkpoint exists if specified
        if parent_checkpoint:
            parent_response = table.get_item(Key={'checkpoint_name': parent_checkpoint})
            if 'Item' not in parent_response:
                return error_response(400, f'Parent checkpoint {parent_checkpoint} not found')

    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    job_name = f"capa-retrain-{timestamp}"

    # Build input data config
    input_data_config = [
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
                    'S3Uri': f's3://{TRAINING_BUCKET}/golden/test/',
                    'S3DataDistributionType': 'FullyReplicated'
                }
            }
        }
    ]

    # If parent checkpoint specified, add pretrained model channel
    if parent_checkpoint:
        input_data_config.append({
            'ChannelName': 'pretrained',
            'DataSource': {
                'S3DataSource': {
                    'S3DataType': 'S3Prefix',
                    'S3Uri': f's3://{MODEL_BUCKET}/checkpoints/{parent_checkpoint}/',
                    'S3DataDistributionType': 'FullyReplicated'
                }
            }
        })

    training_config = {
        'TrainingJobName': job_name,
        'RoleArn': ROLE_ARN,
        'AlgorithmSpecification': {
            'TrainingImage': IMAGE_URI,
            'TrainingInputMode': 'File',
            'MetricDefinitions': [
                {'Name': 'train:loss', 'Regex': r'train_loss=([0-9\\.]+);'},
                {'Name': 'test:accuracy', 'Regex': r'test_accuracy=([0-9\\.]+);'}
            ]
        },
        'InputDataConfig': input_data_config,
        'OutputDataConfig': {
            'S3OutputPath': f's3://{MODEL_BUCKET}/checkpoints/{checkpoint_name}/'
        },
        'ResourceConfig': {
            'InstanceType': 'ml.m5.xlarge',
            'InstanceCount': 1,
            'VolumeSizeInGB': 30
        },
        'StoppingCondition': {
            'MaxRuntimeInSeconds': 3600
        },
        'HyperParameters': {
            'epochs': str(epochs),
            'batch_size': str(batch_size),
            'learning_rate': str(learning_rate),
            'checkpoint_name': checkpoint_name,
            'parent_checkpoint': parent_checkpoint or '',
            'is_golden': 'false'
        }
    }

    response = sagemaker.create_training_job(**training_config)

    # Create pending checkpoint entry
    if CHECKPOINTS_TABLE:
        table = dynamodb.Table(CHECKPOINTS_TABLE)
        table.put_item(Item={
            'checkpoint_name': checkpoint_name,
            'status': 'training',
            'is_golden': False,
            'is_active': 'false',
            'parent_checkpoint': parent_checkpoint or 'none',
            'training_job_name': job_name,
            'created_at': datetime.now().isoformat(),
            'epochs': epochs,
            'batch_size': batch_size,
            'learning_rate': Decimal(str(learning_rate)),
            'reason': reason,
            'training_data_source': 'approved_feedback'
        })

    return success_response({
        'message': 'Training job started',
        'job_name': job_name,
        'checkpoint_name': checkpoint_name,
        'parent_checkpoint': parent_checkpoint,
        'reason': reason,
        'config': {
            'epochs': epochs,
            'batch_size': batch_size,
            'learning_rate': learning_rate
        },
        'status_url': f'https://console.aws.amazon.com/sagemaker/home?region=us-east-1#/jobs/{job_name}'
    })


def _convert_to_decimal(obj):
    """Convert floats to Decimal for DynamoDB compatibility"""
    if isinstance(obj, float):
        return Decimal(str(obj))
    elif isinstance(obj, dict):
        return {k: _convert_to_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_to_decimal(i) for i in obj]
    return obj


def register_checkpoint(job_name):
    """Register a completed training job as a checkpoint"""
    if not job_name:
        return error_response(400, 'job_name is required')

    try:
        # Get training job details
        job_response = sagemaker.describe_training_job(TrainingJobName=job_name)
        status = job_response['TrainingJobStatus']

        if status != 'Completed':
            return error_response(400, f'Training job is not completed. Current status: {status}')

        # Get the output path
        model_artifacts = job_response.get('ModelArtifacts', {}).get('S3ModelArtifacts', '')

        # Extract checkpoint name from hyperparameters
        hyperparameters = job_response.get('HyperParameters', {})
        checkpoint_name = hyperparameters.get('checkpoint_name', '')

        if not checkpoint_name:
            return error_response(400, 'Could not determine checkpoint name from training job')

        # Extract metadata from model.tar.gz artifact
        metadata = {}
        try:
            # model_artifacts is the full S3 URI to model.tar.gz
            # e.g. s3://bucket/checkpoints/name/job/output/model.tar.gz
            if model_artifacts:
                # Parse S3 URI
                parts = model_artifacts.replace('s3://', '').split('/', 1)
                artifact_bucket = parts[0]
                artifact_key = parts[1]

                # Download and extract tar.gz to /tmp
                tar_path = '/tmp/model.tar.gz'
                extract_dir = '/tmp/model_extract'

                s3.download_file(artifact_bucket, artifact_key, tar_path)

                # Clean up any previous extraction
                if os.path.exists(extract_dir):
                    shutil.rmtree(extract_dir)
                os.makedirs(extract_dir, exist_ok=True)

                with tarfile.open(tar_path, 'r:gz') as tar:
                    tar.extractall(path=extract_dir)

                # Read model_metadata.json from extracted contents
                metadata_path = os.path.join(extract_dir, 'model_metadata.json')
                if os.path.exists(metadata_path):
                    with open(metadata_path) as f:
                        metadata = json.loads(f.read())
                    print(f"Successfully read metadata: accuracy={metadata.get('accuracy')}")
                else:
                    print(f"model_metadata.json not found in tar.gz. Contents: {os.listdir(extract_dir)}")

                # Cleanup
                os.remove(tar_path)
                shutil.rmtree(extract_dir, ignore_errors=True)
        except Exception as e:
            print(f"Could not extract metadata from model.tar.gz: {e}")

        # Update checkpoint in DynamoDB
        if CHECKPOINTS_TABLE:
            table = dynamodb.Table(CHECKPOINTS_TABLE)

            update_expr = 'SET #status = :status, completed_at = :completed'
            expr_values = {
                ':status': 'completed',
                ':completed': datetime.now().isoformat()
            }
            expr_names = {'#status': 'status'}

            if model_artifacts:
                update_expr += ', model_artifacts = :ma'
                expr_values[':ma'] = model_artifacts

            if metadata:
                update_expr += ', accuracy = :acc, final_loss = :loss, confusion_matrix = :cm, per_class_metrics = :pcm, class_names = :cn, training_history = :th, epochs_trained = :et, training_samples = :ts, test_samples = :tes'
                expr_values[':acc'] = Decimal(str(metadata.get('accuracy', 0)))
                expr_values[':loss'] = Decimal(str(metadata.get('final_loss', 0))) if metadata.get('final_loss') else None
                expr_values[':cm'] = _convert_to_decimal(metadata.get('confusion_matrix', []))
                expr_values[':pcm'] = _convert_to_decimal(metadata.get('per_class_metrics', {}))
                expr_values[':cn'] = metadata.get('class_names', [])
                expr_values[':th'] = _convert_to_decimal(metadata.get('training_history', []))
                expr_values[':et'] = metadata.get('epochs_trained', 0)
                expr_values[':ts'] = metadata.get('training_samples', 0)
                expr_values[':tes'] = metadata.get('test_samples', 0)

            table.update_item(
                Key={'checkpoint_name': checkpoint_name},
                UpdateExpression=update_expr,
                ExpressionAttributeNames=expr_names,
                ExpressionAttributeValues=expr_values
            )

        return success_response({
            'message': f'Checkpoint {checkpoint_name} registered successfully',
            'checkpoint_name': checkpoint_name,
            'accuracy': metadata.get('accuracy'),
            'model_artifacts': model_artifacts
        })

    except sagemaker.exceptions.ClientError as e:
        return error_response(404, f'Training job {job_name} not found')
    except Exception as e:
        return error_response(500, f'Failed to register checkpoint: {str(e)}')


def success_response(data):
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
        },
        'body': json.dumps(data)
    }


def error_response(status_code, message):
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
        },
        'body': json.dumps({'error': message})
    }
