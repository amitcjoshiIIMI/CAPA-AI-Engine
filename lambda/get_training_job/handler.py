import json
import boto3

sagemaker = boto3.client('sagemaker', region_name='us-east-1')


def lambda_handler(event, context):
    """
    GET /training-jobs/{job_name}

    Returns detailed information about a specific training job.
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

        # Describe the training job
        response = sagemaker.describe_training_job(TrainingJobName=job_name)

        # Extract relevant fields
        job_details = {
            'job_name': response['TrainingJobName'],
            'status': response['TrainingJobStatus'],
            'secondary_status': response.get('SecondaryStatus'),
            'created': response['CreationTime'].isoformat(),
            'last_modified': response['LastModifiedTime'].isoformat(),
            'end_time': response.get('TrainingEndTime', '').isoformat() if response.get('TrainingEndTime') else None,
            'failure_reason': response.get('FailureReason'),
            'hyperparameters': response.get('HyperParameters', {}),
            'resource_config': {
                'instance_type': response['ResourceConfig']['InstanceType'],
                'instance_count': response['ResourceConfig']['InstanceCount'],
                'volume_size_gb': response['ResourceConfig']['VolumeSizeInGB']
            },
            'input_data_config': [
                {
                    'channel_name': channel['ChannelName'],
                    's3_uri': channel['DataSource']['S3DataSource']['S3Uri']
                }
                for channel in response.get('InputDataConfig', [])
            ],
            'output_path': response['OutputDataConfig']['S3OutputPath'],
            'model_artifacts': response.get('ModelArtifacts', {}).get('S3ModelArtifacts'),
            'billable_seconds': response.get('BillableTimeInSeconds'),
            'training_time_seconds': response.get('TrainingTimeInSeconds'),
            'status_url': f"https://console.aws.amazon.com/sagemaker/home?region=us-east-1#/jobs/{job_name}"
        }

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps(job_details, default=str)
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
