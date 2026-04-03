import json
import boto3
import os
from datetime import datetime
from decimal import Decimal

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
s3 = boto3.client('s3', region_name='us-east-1')

CHECKPOINTS_TABLE = os.environ['CHECKPOINTS_TABLE']
MODEL_BUCKET = os.environ['MODEL_BUCKET']

table = dynamodb.Table(CHECKPOINTS_TABLE)


class DecimalEncoder(json.JSONEncoder):
    """Handle Decimal types from DynamoDB"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def lambda_handler(event, context):
    """
    Checkpoint Management Handler

    Endpoints:
    - GET /checkpoints - List all checkpoints
    - GET /checkpoints/active - Get current active checkpoint
    - GET /checkpoints/lineage - Get lineage graph data
    - GET /checkpoints/{name} - Get specific checkpoint details
    - POST /checkpoints/active - Set active checkpoint
    - DELETE /checkpoints/{name} - Delete a checkpoint
    """
    try:
        http_method = event.get('httpMethod', 'GET')
        path = event.get('path', '')
        path_params = event.get('pathParameters') or {}
        checkpoint_name = path_params.get('name')

        # Route handling
        if http_method == 'GET':
            if '/active' in path:
                return get_active_checkpoint()
            elif '/lineage' in path:
                return get_lineage_graph()
            elif checkpoint_name:
                return get_checkpoint(checkpoint_name)
            else:
                return list_checkpoints()
        elif http_method == 'POST':
            if '/active' in path:
                body = json.loads(event.get('body', '{}'))
                return set_active_checkpoint(body.get('checkpoint_name'))
            else:
                return error_response(400, 'Invalid POST endpoint')
        elif http_method == 'DELETE':
            if checkpoint_name:
                return delete_checkpoint(checkpoint_name)
            return error_response(400, 'Checkpoint name required')
        else:
            return error_response(405, f'Method {http_method} not allowed')

    except Exception as e:
        print(f"Error: {str(e)}")
        return error_response(500, str(e))


def list_checkpoints():
    """List all checkpoints with their metrics"""
    try:
        response = table.scan()
        checkpoints = response.get('Items', [])

        # Sort by created_at descending
        checkpoints.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        return success_response({
            'checkpoints': checkpoints,
            'count': len(checkpoints)
        })
    except Exception as e:
        return error_response(500, f'Failed to list checkpoints: {str(e)}')


def get_checkpoint(checkpoint_name):
    """Get detailed checkpoint information including confusion matrix"""
    try:
        response = table.get_item(Key={'checkpoint_name': checkpoint_name})
        checkpoint = response.get('Item')

        if not checkpoint:
            return error_response(404, f'Checkpoint {checkpoint_name} not found')

        # Try to fetch confusion matrix from S3 if not in DynamoDB
        if 'confusion_matrix' not in checkpoint:
            try:
                s3_key = f"checkpoints/{checkpoint_name}/confusion_matrix.json"
                obj = s3.get_object(Bucket=MODEL_BUCKET, Key=s3_key)
                cm_data = json.loads(obj['Body'].read().decode('utf-8'))
                checkpoint['confusion_matrix'] = cm_data.get('matrix')
                checkpoint['per_class_metrics'] = cm_data.get('per_class_metrics')
            except:
                pass

        return success_response(checkpoint)
    except Exception as e:
        return error_response(500, f'Failed to get checkpoint: {str(e)}')


def get_active_checkpoint():
    """Get the currently active checkpoint"""
    try:
        # Query using the ActiveIndex
        response = table.query(
            IndexName='ActiveIndex',
            KeyConditionExpression='is_active = :active',
            ExpressionAttributeValues={':active': 'true'},
            Limit=1
        )

        items = response.get('Items', [])
        if not items:
            return success_response({'active_checkpoint': None})

        return success_response({'active_checkpoint': items[0]})
    except Exception as e:
        return error_response(500, f'Failed to get active checkpoint: {str(e)}')


def set_active_checkpoint(checkpoint_name):
    """Set a checkpoint as the active model for inference"""
    if not checkpoint_name:
        return error_response(400, 'checkpoint_name is required')

    try:
        # Verify checkpoint exists
        response = table.get_item(Key={'checkpoint_name': checkpoint_name})
        if 'Item' not in response:
            return error_response(404, f'Checkpoint {checkpoint_name} not found')

        # First, unset any currently active checkpoint
        active_response = table.query(
            IndexName='ActiveIndex',
            KeyConditionExpression='is_active = :active',
            ExpressionAttributeValues={':active': 'true'}
        )

        for item in active_response.get('Items', []):
            table.update_item(
                Key={'checkpoint_name': item['checkpoint_name']},
                UpdateExpression='SET is_active = :inactive',
                ExpressionAttributeValues={':inactive': 'false'}
            )

        # Set the new checkpoint as active
        table.update_item(
            Key={'checkpoint_name': checkpoint_name},
            UpdateExpression='SET is_active = :active, activated_at = :time',
            ExpressionAttributeValues={
                ':active': 'true',
                ':time': datetime.now().isoformat()
            }
        )

        # Copy model files to root of model bucket for inference Lambda
        copy_checkpoint_to_active(checkpoint_name)

        return success_response({
            'message': f'Checkpoint {checkpoint_name} is now active',
            'checkpoint_name': checkpoint_name,
            'activated_at': datetime.now().isoformat()
        })
    except Exception as e:
        return error_response(500, f'Failed to set active checkpoint: {str(e)}')


def copy_checkpoint_to_active(checkpoint_name):
    """Copy checkpoint files to root for inference Lambda"""
    try:
        # Copy model.pth
        s3.copy_object(
            CopySource={'Bucket': MODEL_BUCKET, 'Key': f'checkpoints/{checkpoint_name}/model.pth'},
            Bucket=MODEL_BUCKET,
            Key='model.pth'
        )

        # Copy model_metadata.json
        s3.copy_object(
            CopySource={'Bucket': MODEL_BUCKET, 'Key': f'checkpoints/{checkpoint_name}/model_metadata.json'},
            Bucket=MODEL_BUCKET,
            Key='model_metadata.json'
        )

        print(f"Copied checkpoint {checkpoint_name} to active model location")
    except Exception as e:
        print(f"Warning: Failed to copy checkpoint files: {str(e)}")
        raise


def get_lineage_graph():
    """Get lineage data for visualization as a directed graph"""
    try:
        response = table.scan()
        checkpoints = response.get('Items', [])

        # Build nodes and edges for the graph
        nodes = []
        edges = []

        for cp in checkpoints:
            node = {
                'id': cp['checkpoint_name'],
                'label': cp['checkpoint_name'],
                'accuracy': float(cp.get('accuracy', 0)),
                'loss': float(cp.get('final_loss', 0)) if cp.get('final_loss') else None,
                'is_golden': cp.get('is_golden', False),
                'is_active': cp.get('is_active', 'false') == 'true',
                'created_at': cp.get('created_at', ''),
                'epochs': int(cp.get('epochs', 0)),
            }
            nodes.append(node)

            # Create edge from parent to this checkpoint
            parent = cp.get('parent_checkpoint')
            if parent:
                edges.append({
                    'source': parent,
                    'target': cp['checkpoint_name']
                })

        # Sort nodes by created_at for consistent ordering
        nodes.sort(key=lambda x: x.get('created_at', ''))

        return success_response({
            'nodes': nodes,
            'edges': edges
        })
    except Exception as e:
        return error_response(500, f'Failed to get lineage graph: {str(e)}')


def delete_checkpoint(checkpoint_name):
    """Delete a checkpoint"""
    try:
        # Get checkpoint first
        response = table.get_item(Key={'checkpoint_name': checkpoint_name})
        checkpoint = response.get('Item')

        if not checkpoint:
            return error_response(404, f'Checkpoint {checkpoint_name} not found')

        # Don't allow deleting active checkpoint
        if checkpoint.get('is_active', 'false') == 'true':
            return error_response(400, 'Cannot delete the active checkpoint. Set another checkpoint as active first.')

        # Don't allow deleting golden model
        if checkpoint.get('is_golden', False):
            return error_response(400, 'Cannot delete the golden model checkpoint.')

        # Check if this checkpoint has children
        children_response = table.query(
            IndexName='ParentIndex',
            KeyConditionExpression='parent_checkpoint = :parent',
            ExpressionAttributeValues={':parent': checkpoint_name}
        )

        if children_response.get('Items'):
            child_names = [c['checkpoint_name'] for c in children_response['Items']]
            return error_response(400, f'Cannot delete checkpoint with children: {", ".join(child_names)}')

        # Delete from S3
        try:
            # List and delete all files in checkpoint folder
            prefix = f'checkpoints/{checkpoint_name}/'
            list_response = s3.list_objects_v2(Bucket=MODEL_BUCKET, Prefix=prefix)

            for obj in list_response.get('Contents', []):
                s3.delete_object(Bucket=MODEL_BUCKET, Key=obj['Key'])
        except Exception as e:
            print(f"Warning: Failed to delete S3 files: {str(e)}")

        # Delete from DynamoDB
        table.delete_item(Key={'checkpoint_name': checkpoint_name})

        return success_response({
            'message': f'Checkpoint {checkpoint_name} deleted successfully',
            'deleted_at': datetime.now().isoformat()
        })
    except Exception as e:
        return error_response(500, f'Failed to delete checkpoint: {str(e)}')


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
        }, cls=DecimalEncoder)
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
            'error': {'message': message}
        })
    }
