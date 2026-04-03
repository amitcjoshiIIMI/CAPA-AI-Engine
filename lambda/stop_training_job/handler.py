import json
import boto3

sagemaker = boto3.client('sagemaker', region_name='us-east-1')


def lambda_handler(event, context):
    """
    POST /training-jobs/{job_name}/stop

    Stops a running SageMaker training job.
    """
    try:
        # Get job name from path parameters
        path_params = event.get('pathParameters', {}) or {}
        job_name = path_params.get('job_name')

        if not job_name:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'job_name is required'})
            }

        # First check if the job exists and is in a stoppable state
        try:
            job_info = sagemaker.describe_training_job(TrainingJobName=job_name)
            current_status = job_info['TrainingJobStatus']

            if current_status not in ['InProgress', 'Stopping']:
                return {
                    'statusCode': 400,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({
                        'error': f'Cannot stop job with status: {current_status}',
                        'job_name': job_name,
                        'current_status': current_status
                    })
                }
        except sagemaker.exceptions.ResourceNotFound:
            return {
                'statusCode': 404,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': f'Training job {job_name} not found'})
            }

        # Stop the training job
        sagemaker.stop_training_job(TrainingJobName=job_name)

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'job_name': job_name,
                'status': 'Stopping',
                'message': 'Stop request submitted successfully'
            })
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': str(e)})
        }
