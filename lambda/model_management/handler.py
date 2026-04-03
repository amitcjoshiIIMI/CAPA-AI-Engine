import json
import boto3
import os
from datetime import datetime

s3 = boto3.client('s3', region_name='us-east-1')

MODEL_BUCKET = os.environ['MODEL_BUCKET']


def lambda_handler(event, context):
    """
    Model Management Handler

    Endpoints:
    - GET /models - List all model versions
    - GET /models/current - Get current active model info
    - POST /models/{version_id}/rollback - Rollback to a specific model version
    - DELETE /models/{version_id} - Delete a specific model version
    """
    try:
        http_method = event.get('httpMethod', 'GET')
        path_params = event.get('pathParameters') or {}
        resource_path = event.get('resource', '')

        version_id = path_params.get('version_id')

        if http_method == 'GET':
            if 'current' in resource_path:
                return get_current_model()
            else:
                return list_models()
        elif http_method == 'POST' and 'rollback' in resource_path:
            return rollback_model(version_id)
        elif http_method == 'DELETE' and version_id:
            return delete_model(version_id)
        else:
            return error_response(405, f'Method {http_method} not allowed')

    except Exception as e:
        print(f"Error: {str(e)}")
        return error_response(500, str(e))


def get_current_model():
    """Get information about the current active model"""
    try:
        # Get current model.pth info
        model_response = s3.head_object(Bucket=MODEL_BUCKET, Key='model.pth')

        # Get metadata if exists
        metadata = {}
        try:
            metadata_response = s3.get_object(Bucket=MODEL_BUCKET, Key='model_metadata.json')
            metadata = json.loads(metadata_response['Body'].read().decode('utf-8'))
        except:
            pass

        return success_response({
            'version_id': model_response.get('VersionId', 'unknown'),
            'last_modified': model_response['LastModified'].isoformat(),
            'size_bytes': model_response['ContentLength'],
            'etag': model_response['ETag'].strip('"'),
            'metadata': metadata,
            'is_current': True
        })

    except s3.exceptions.ClientError as e:
        if e.response['Error']['Code'] == '404':
            return error_response(404, 'No model found')
        raise


def list_models():
    """List all model versions"""
    try:
        # List all versions of model.pth
        response = s3.list_object_versions(
            Bucket=MODEL_BUCKET,
            Prefix='model.pth'
        )

        models = []
        current_version_id = None

        # Get the current version
        try:
            current_response = s3.head_object(Bucket=MODEL_BUCKET, Key='model.pth')
            current_version_id = current_response.get('VersionId')
        except:
            pass

        for version in response.get('Versions', []):
            if version['Key'] == 'model.pth':
                # Try to get associated metadata for this version
                metadata = {}
                version_id = version.get('VersionId', 'null')

                models.append({
                    'version_id': version_id,
                    'last_modified': version['LastModified'].isoformat(),
                    'size_bytes': version['Size'],
                    'etag': version['ETag'].strip('"'),
                    'is_current': version_id == current_version_id,
                    'is_latest': version.get('IsLatest', False)
                })

        # Sort by last modified (newest first)
        models.sort(key=lambda x: x['last_modified'], reverse=True)

        return success_response({
            'models': models,
            'count': len(models),
            'current_version_id': current_version_id
        })

    except Exception as e:
        print(f"List error: {str(e)}")
        return error_response(500, f'Failed to list models: {str(e)}')


def rollback_model(version_id):
    """Rollback to a specific model version"""
    if not version_id:
        return error_response(400, 'version_id is required')

    try:
        # Verify the version exists
        try:
            s3.head_object(Bucket=MODEL_BUCKET, Key='model.pth', VersionId=version_id)
        except s3.exceptions.ClientError as e:
            if e.response['Error']['Code'] in ['404', 'NoSuchVersion']:
                return error_response(404, f'Model version {version_id} not found')
            raise

        # Copy the old version to create a new "current" version
        copy_source = {
            'Bucket': MODEL_BUCKET,
            'Key': 'model.pth',
            'VersionId': version_id
        }

        response = s3.copy_object(
            CopySource=copy_source,
            Bucket=MODEL_BUCKET,
            Key='model.pth',
            MetadataDirective='COPY'
        )

        new_version_id = response.get('VersionId', 'unknown')

        # Also try to copy the metadata if it exists for that version
        try:
            # For simplicity, we'll update metadata to indicate rollback
            metadata = {
                'rolled_back_from': version_id,
                'rolled_back_at': datetime.now().isoformat(),
                'note': 'Model rolled back to previous version'
            }
            s3.put_object(
                Bucket=MODEL_BUCKET,
                Key='model_metadata.json',
                Body=json.dumps(metadata),
                ContentType='application/json'
            )
        except Exception as e:
            print(f"Failed to update metadata: {e}")

        return success_response({
            'message': 'Model rolled back successfully',
            'previous_version_id': version_id,
            'new_version_id': new_version_id,
            'rolled_back_at': datetime.now().isoformat()
        })

    except Exception as e:
        print(f"Rollback error: {str(e)}")
        return error_response(500, f'Failed to rollback model: {str(e)}')


def delete_model(version_id):
    """Delete a specific model version"""
    if not version_id:
        return error_response(400, 'version_id is required')

    try:
        # Check if this is the current version
        try:
            current_response = s3.head_object(Bucket=MODEL_BUCKET, Key='model.pth')
            current_version_id = current_response.get('VersionId')

            if version_id == current_version_id:
                return error_response(400, 'Cannot delete the current active model version. Rollback to a different version first.')
        except:
            pass

        # Delete the specific version
        s3.delete_object(
            Bucket=MODEL_BUCKET,
            Key='model.pth',
            VersionId=version_id
        )

        return success_response({
            'message': 'Model version deleted successfully',
            'deleted_version_id': version_id,
            'deleted_at': datetime.now().isoformat()
        })

    except s3.exceptions.ClientError as e:
        if e.response['Error']['Code'] in ['404', 'NoSuchVersion']:
            return error_response(404, f'Model version {version_id} not found')
        raise
    except Exception as e:
        print(f"Delete error: {str(e)}")
        return error_response(500, f'Failed to delete model: {str(e)}')


def success_response(data):
    """Return a success response"""
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Access-Control-Allow-Methods': 'GET,POST,DELETE,OPTIONS'
        },
        'body': json.dumps({
            'success': True,
            'data': data
        })
    }


def error_response(status_code, message):
    """Return an error response"""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Access-Control-Allow-Methods': 'GET,POST,DELETE,OPTIONS'
        },
        'body': json.dumps({
            'success': False,
            'error': {
                'message': message
            }
        })
    }
