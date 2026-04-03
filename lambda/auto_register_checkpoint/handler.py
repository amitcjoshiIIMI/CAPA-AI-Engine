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

MODEL_BUCKET = os.environ['MODEL_BUCKET']
CHECKPOINTS_TABLE = os.environ.get('CHECKPOINTS_TABLE', '')


def _convert_to_decimal(obj):
    """Convert floats to Decimal for DynamoDB compatibility"""
    if isinstance(obj, float):
        return Decimal(str(obj))
    elif isinstance(obj, dict):
        return {k: _convert_to_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_to_decimal(i) for i in obj]
    return obj


def lambda_handler(event, context):
    """
    Auto-register checkpoint when SageMaker training job completes.
    Triggered by EventBridge rule on SageMaker TrainingJobStatus change.
    """
    print(f"Received event: {json.dumps(event)}")

    try:
        # Extract job name from EventBridge event
        detail = event.get('detail', {})
        job_name = detail.get('TrainingJobName', '')
        status = detail.get('TrainingJobStatus', '')

        if not job_name:
            print("No TrainingJobName in event, skipping")
            return {'statusCode': 200, 'body': 'No job name'}

        # Only process completed CAPA training jobs
        if not job_name.startswith('capa-'):
            print(f"Job {job_name} is not a CAPA job, skipping")
            return {'statusCode': 200, 'body': 'Not a CAPA job'}

        if status != 'Completed':
            print(f"Job {job_name} status is {status}, not Completed. Skipping.")
            # If job failed/stopped, update checkpoint status
            if status in ('Failed', 'Stopped') and CHECKPOINTS_TABLE:
                _update_checkpoint_status(job_name, status.lower())
            return {'statusCode': 200, 'body': f'Job status: {status}'}

        # Get full training job details
        job_response = sagemaker.describe_training_job(TrainingJobName=job_name)
        model_artifacts = job_response.get('ModelArtifacts', {}).get('S3ModelArtifacts', '')
        hyperparameters = job_response.get('HyperParameters', {})
        checkpoint_name = hyperparameters.get('checkpoint_name', '')

        if not checkpoint_name:
            print(f"No checkpoint_name in hyperparameters for {job_name}")
            return {'statusCode': 200, 'body': 'No checkpoint name'}

        print(f"Auto-registering checkpoint: {checkpoint_name} from job: {job_name}")

        # Extract metadata and model files from model.tar.gz
        metadata = _extract_metadata(model_artifacts, checkpoint_name)

        # Update DynamoDB
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
                expr_values[':loss'] = Decimal(str(metadata.get('final_loss', 0))) if metadata.get('final_loss') else Decimal('0')
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

            print(f"Checkpoint {checkpoint_name} registered. Accuracy: {metadata.get('accuracy', 'N/A')}")

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f'Checkpoint {checkpoint_name} auto-registered',
                'accuracy': str(metadata.get('accuracy')) if metadata else None
            })
        }

    except Exception as e:
        print(f"Error auto-registering checkpoint: {str(e)}")
        return {'statusCode': 500, 'body': str(e)}


def _extract_metadata(model_artifacts, checkpoint_name=''):
    """Download and extract model_metadata.json from model.tar.gz.
    Also copies model.pth and model_metadata.json to checkpoints/{name}/
    so that set_active_checkpoint can copy them to the bucket root."""
    if not model_artifacts:
        return {}

    try:
        parts = model_artifacts.replace('s3://', '').split('/', 1)
        artifact_bucket = parts[0]
        artifact_key = parts[1]

        tar_path = '/tmp/model.tar.gz'
        extract_dir = '/tmp/model_extract'

        s3.download_file(artifact_bucket, artifact_key, tar_path)

        if os.path.exists(extract_dir):
            shutil.rmtree(extract_dir)
        os.makedirs(extract_dir, exist_ok=True)

        with tarfile.open(tar_path, 'r:gz') as tar:
            tar.extractall(path=extract_dir)

        # Copy extracted files to checkpoints/{name}/ in S3
        # so copy_checkpoint_to_active() can find them later
        if checkpoint_name:
            for filename in ('model.pth', 'model_metadata.json', 'confusion_matrix.json'):
                local_path = os.path.join(extract_dir, filename)
                if os.path.exists(local_path):
                    s3_key = f'checkpoints/{checkpoint_name}/{filename}'
                    s3.upload_file(local_path, MODEL_BUCKET, s3_key)
                    print(f"Uploaded {filename} to s3://{MODEL_BUCKET}/{s3_key}")

        metadata_path = os.path.join(extract_dir, 'model_metadata.json')
        if os.path.exists(metadata_path):
            with open(metadata_path) as f:
                metadata = json.loads(f.read())
            print(f"Extracted metadata: accuracy={metadata.get('accuracy')}")
            return metadata
        else:
            print(f"model_metadata.json not found. Contents: {os.listdir(extract_dir)}")
            return {}

    except Exception as e:
        print(f"Failed to extract metadata: {e}")
        return {}
    finally:
        # Cleanup
        if os.path.exists('/tmp/model.tar.gz'):
            os.remove('/tmp/model.tar.gz')
        if os.path.exists('/tmp/model_extract'):
            shutil.rmtree('/tmp/model_extract', ignore_errors=True)


def _update_checkpoint_status(job_name, status):
    """Update checkpoint status when job fails/stops"""
    try:
        job_response = sagemaker.describe_training_job(TrainingJobName=job_name)
        checkpoint_name = job_response.get('HyperParameters', {}).get('checkpoint_name', '')
        if checkpoint_name and CHECKPOINTS_TABLE:
            table = dynamodb.Table(CHECKPOINTS_TABLE)
            table.update_item(
                Key={'checkpoint_name': checkpoint_name},
                UpdateExpression='SET #status = :status, completed_at = :completed',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':status': status,
                    ':completed': datetime.now().isoformat()
                }
            )
            print(f"Updated checkpoint {checkpoint_name} status to {status}")
    except Exception as e:
        print(f"Failed to update checkpoint status: {e}")
