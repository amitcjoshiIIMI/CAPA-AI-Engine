import json
import boto3
from datetime import datetime, timedelta

cloudwatch = boto3.client('cloudwatch', region_name='us-east-1')
sagemaker = boto3.client('sagemaker', region_name='us-east-1')


def lambda_handler(event, context):
    """
    GET /training-jobs/{job_name}/metrics

    Returns training metrics (loss, accuracy, epoch) for a job.
    """
    try:
        path_params = event.get('pathParameters', {}) or {}
        job_name = path_params.get('job_name')

        if not job_name:
            return error_response(400, 'job_name is required')

        # Get job info for time range
        job = sagemaker.describe_training_job(TrainingJobName=job_name)
        start_time = job['CreationTime']
        end_time = job.get('TrainingEndTime', datetime.utcnow())
        total_epochs = int(job.get('HyperParameters', {}).get('epochs', '10'))

        # Fetch metrics from CloudWatch
        metrics = {}
        for metric_name in ['train:loss', 'test:accuracy']:
            response = cloudwatch.get_metric_statistics(
                Namespace='/aws/sagemaker/TrainingJobs',
                MetricName=metric_name,
                Dimensions=[
                    {'Name': 'TrainingJobName', 'Value': job_name}
                ],
                StartTime=start_time,
                EndTime=end_time + timedelta(minutes=5),
                Period=60,
                Statistics=['Average']
            )
            metrics[metric_name] = sorted(
                response['Datapoints'],
                key=lambda x: x['Timestamp']
            )

        # Calculate current epoch from data points
        current_epoch = len(metrics.get('train:loss', []))
        progress_percent = (current_epoch / total_epochs * 100) if total_epochs > 0 else 0

        # Format response
        data_points = []
        loss_points = metrics.get('train:loss', [])
        accuracy_points = metrics.get('test:accuracy', [])

        for i in range(max(len(loss_points), len(accuracy_points))):
            point = {
                'epoch': i + 1,
                'timestamp': None,
                'loss': None,
                'accuracy': None
            }
            if i < len(loss_points):
                point['loss'] = loss_points[i]['Average']
                point['timestamp'] = loss_points[i]['Timestamp'].isoformat()
            if i < len(accuracy_points):
                point['accuracy'] = accuracy_points[i]['Average']
                if not point['timestamp']:
                    point['timestamp'] = accuracy_points[i]['Timestamp'].isoformat()
            data_points.append(point)

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'job_name': job_name,
                'status': job['TrainingJobStatus'],
                'current_epoch': current_epoch,
                'total_epochs': total_epochs,
                'progress_percent': round(progress_percent, 1),
                'metrics': data_points
            }, default=str)
        }

    except sagemaker.exceptions.ResourceNotFound:
        return error_response(404, f'Training job {job_name} not found')
    except Exception as e:
        print(f"Error: {str(e)}")
        return error_response(500, str(e))


def error_response(status_code, message):
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps({'error': message})
    }
