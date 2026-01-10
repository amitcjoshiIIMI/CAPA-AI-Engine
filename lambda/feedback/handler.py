import json
import boto3
import os
from datetime import datetime
from decimal import Decimal

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
FEEDBACK_TABLE = os.environ['FEEDBACK_TABLE']


class DecimalEncoder(json.JSONEncoder):
    """Custom JSON encoder for DynamoDB Decimal values"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)


def lambda_handler(event, context):
    """
    Feedback Handler

    Endpoints:
    - POST /feedback - Create new feedback
    - GET /feedback - List all feedback
    - GET /feedback/{image_id}/{timestamp} - Get specific feedback
    - PATCH /feedback/{image_id}/{timestamp} - Mark as reviewed
    """
    try:
        http_method = event.get('httpMethod', 'POST')
        path_params = event.get('pathParameters') or {}

        image_id = path_params.get('image_id')
        timestamp = path_params.get('timestamp')

        if http_method == 'POST':
            return create_feedback(event)
        elif http_method == 'GET':
            if image_id and timestamp:
                return get_feedback(image_id, timestamp)
            elif image_id:
                return list_feedback_for_image(image_id)
            else:
                return list_all_feedback(event)
        elif http_method == 'PATCH':
            if image_id and timestamp:
                return update_feedback(image_id, timestamp, event)
            else:
                return error_response(400, 'image_id and timestamp required for PATCH')
        else:
            return error_response(405, f'Method {http_method} not allowed')

    except Exception as e:
        print(f"Error: {str(e)}")
        return error_response(500, str(e))


def create_feedback(event):
    """
    POST /feedback - Create new feedback

    Expected input:
    {
        "image_id": "Cr_1.bmp",
        "predicted_class": "Crazing",
        "user_action": "agree" | "disagree",
        "corrected_class": "Scratches" (only if disagree),
        "confidence": "0.98",
        "user_id": "user123" (optional)
    }
    """
    body = json.loads(event['body']) if 'body' in event else event

    image_id = body['image_id']
    predicted_class = body['predicted_class']
    user_action = body['user_action']  # "agree" or "disagree"
    confidence = body.get('confidence', '0.0')
    user_id = body.get('user_id', 'anonymous')
    s3_key = body.get('s3_key')

    # Validation
    if user_action not in ['agree', 'disagree']:
        return error_response(400, 'user_action must be "agree" or "disagree"')

    feedback_record = {
        'image_id': image_id,
        'timestamp': datetime.now().isoformat(),
        'predicted_class': predicted_class,
        'user_action': user_action,
        'confidence': confidence,
        'user_id': user_id,
        'needs_expert_review': False,
        's3_key': s3_key
    }

    # If user disagrees, capture corrected class
    if user_action == 'disagree':
        if 'corrected_class' not in body:
            return error_response(400, 'corrected_class required when user_action=disagree')
        feedback_record['corrected_class'] = body['corrected_class']
        feedback_record['needs_expert_review'] = True

    # Also flag low confidence for review
    if float(confidence) < 0.90:
        feedback_record['needs_expert_review'] = True
        feedback_record['review_reason'] = 'Low confidence'

    # Save to DynamoDB
    table = dynamodb.Table(FEEDBACK_TABLE)
    table.put_item(Item=json.loads(json.dumps(feedback_record), parse_float=Decimal))

    return success_response({
        'message': 'Feedback recorded',
        'feedback_id': f"{image_id}_{feedback_record['timestamp']}",
        'needs_expert_review': feedback_record['needs_expert_review']
    })


def get_feedback(image_id, timestamp):
    """GET /feedback/{image_id}/{timestamp} - Get specific feedback"""
    table = dynamodb.Table(FEEDBACK_TABLE)

    response = table.get_item(
        Key={
            'image_id': image_id,
            'timestamp': timestamp
        }
    )

    if 'Item' not in response:
        return error_response(404, f'Feedback not found for {image_id}/{timestamp}')

    return success_response(response['Item'])


def list_feedback_for_image(image_id):
    """GET /feedback/{image_id} - List all feedback for an image"""
    table = dynamodb.Table(FEEDBACK_TABLE)

    response = table.query(
        KeyConditionExpression='image_id = :iid',
        ExpressionAttributeValues={':iid': image_id}
    )

    items = response.get('Items', [])
    items.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

    return success_response({
        'image_id': image_id,
        'feedback': items,
        'count': len(items)
    })


def list_all_feedback(event):
    """GET /feedback - List all feedback with optional filters"""
    query_params = event.get('queryStringParameters') or {}
    needs_review = query_params.get('needs_review')
    limit = int(query_params.get('limit', 50))

    table = dynamodb.Table(FEEDBACK_TABLE)

    scan_kwargs = {'Limit': min(limit, 100)}

    if needs_review == 'true':
        scan_kwargs['FilterExpression'] = 'needs_expert_review = :val'
        scan_kwargs['ExpressionAttributeValues'] = {':val': True}

    response = table.scan(**scan_kwargs)
    items = response.get('Items', [])

    # Sort by timestamp descending
    items.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

    return success_response({
        'feedback': items,
        'count': len(items)
    })


def update_feedback(image_id, timestamp, event):
    """
    PATCH /feedback/{image_id}/{timestamp} - Mark feedback as reviewed

    Expected input:
    {
        "reviewed": true,
        "reviewer_id": "expert123",
        "notes": "Verified correct classification"
    }
    """
    body = json.loads(event['body']) if 'body' in event else event

    table = dynamodb.Table(FEEDBACK_TABLE)

    # Check if feedback exists
    response = table.get_item(
        Key={
            'image_id': image_id,
            'timestamp': timestamp
        }
    )

    if 'Item' not in response:
        return error_response(404, f'Feedback not found for {image_id}/{timestamp}')

    # Build update expression
    update_parts = []
    expression_values = {}

    if 'reviewed' in body:
        update_parts.append('reviewed = :reviewed')
        expression_values[':reviewed'] = body['reviewed']

    if 'reviewer_id' in body:
        update_parts.append('reviewer_id = :reviewer_id')
        expression_values[':reviewer_id'] = body['reviewer_id']

    if 'notes' in body:
        update_parts.append('review_notes = :notes')
        expression_values[':notes'] = body['notes']

    # Always add review timestamp
    update_parts.append('reviewed_at = :reviewed_at')
    expression_values[':reviewed_at'] = datetime.now().isoformat()

    # If marked as reviewed, clear the needs_expert_review flag
    if body.get('reviewed') is True:
        update_parts.append('needs_expert_review = :needs_review')
        expression_values[':needs_review'] = False

    if not update_parts:
        return error_response(400, 'No fields to update')

    update_expression = 'SET ' + ', '.join(update_parts)

    # Update the item
    table.update_item(
        Key={
            'image_id': image_id,
            'timestamp': timestamp
        },
        UpdateExpression=update_expression,
        ExpressionAttributeValues=expression_values
    )

    return success_response({
        'message': 'Feedback updated',
        'image_id': image_id,
        'timestamp': timestamp,
        'reviewed': body.get('reviewed', False),
        'reviewed_at': expression_values[':reviewed_at']
    })


def success_response(data):
    """Return a success response"""
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
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
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps({
            'success': False,
            'error': {
                'message': message
            }
        })
    }
