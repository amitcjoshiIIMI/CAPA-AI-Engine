import json
import boto3
import os
from datetime import datetime
from decimal import Decimal

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
FEEDBACK_TABLE = os.environ['FEEDBACK_TABLE']


def lambda_handler(event, context):
    """
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
    try:
        body = json.loads(event['body']) if 'body' in event else event
        
        image_id = body['image_id']
        predicted_class = body['predicted_class']
        user_action = body['user_action']  # "agree" or "disagree"
        confidence = body.get('confidence', '0.0')
        user_id = body.get('user_id', 'anonymous')
        s3_key = body.get('s3_key')  # Add this line
        # Validation
        if user_action not in ['agree', 'disagree']:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'user_action must be "agree" or "disagree"'})
            }
        
        feedback_record = {
            'image_id': image_id,
            'timestamp': datetime.now().isoformat(),
            'predicted_class': predicted_class,
            'user_action': user_action,
            'confidence': confidence,
            'user_id': user_id,
            'needs_expert_review': False,
            's3_key': s3_key  # Add this line
        }
        
        # If user disagrees, capture corrected class
        if user_action == 'disagree':
            if 'corrected_class' not in body:
                return {
                    'statusCode': 400,
                    'body': json.dumps({'error': 'corrected_class required when user_action=disagree'})
                }
            feedback_record['corrected_class'] = body['corrected_class']
            feedback_record['needs_expert_review'] = True
        
        # Also flag low confidence for review
        if float(confidence) < 0.90:
            feedback_record['needs_expert_review'] = True
            feedback_record['review_reason'] = 'Low confidence'
        
        # Save to DynamoDB
        table = dynamodb.Table(FEEDBACK_TABLE)
        table.put_item(Item=json.loads(json.dumps(feedback_record), parse_float=Decimal))
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Feedback recorded',
                'feedback_id': f"{image_id}_{feedback_record['timestamp']}",
                'needs_expert_review': feedback_record['needs_expert_review']
            })
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }