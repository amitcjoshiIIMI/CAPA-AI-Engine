import json
import boto3
import os
import base64
from decimal import Decimal
from datetime import datetime

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
s3 = boto3.client('s3', region_name='us-east-1')

FEEDBACK_TABLE = os.environ['FEEDBACK_TABLE']
IMAGES_BUCKET = os.environ['IMAGES_BUCKET']
TRAINING_BUCKET = os.environ['TRAINING_BUCKET']

# Class names for validation
VALID_CLASSES = [
    'Crazing', 'Inclusion', 'Patches', 
    'Pitted_Surface', 'Rolled-in_Scale', 'Scratches'
]


def lambda_handler(event, context):
    """
    POST /expert-approve
    Input:
    {
        "image_id": "Sc_1.bmp",
        "feedback_timestamp": "2026-01-05T17:09:45.857740",
        "action": "approve" | "reject",
        "corrected_class": "Scratches",  # Final class after expert review
        "notes": "Expert verified - actually scratches not crazing"
    }
    
    Actions:
    - If approve: Move image to training_bucket/approved/train/{corrected_class}/
    - Update feedback record with expert decision
    - Track image count per class
    """
    try:
        body = json.loads(event['body']) if 'body' in event else event
        
        image_id = body['image_id']
        feedback_timestamp = body['feedback_timestamp']
        action = body['action']  # "approve" or "reject"
        corrected_class = body.get('corrected_class')
        notes = body.get('notes', '')
        
        # Validation
        if action not in ['approve', 'reject']:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'action must be "approve" or "reject"'})
            }
        
        if action == 'approve' and not corrected_class:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'corrected_class required when action=approve'})
            }
        
        if corrected_class and corrected_class not in VALID_CLASSES:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': f'Invalid class. Must be one of: {VALID_CLASSES}'
                })
            }
        
        # Get feedback record
        table = dynamodb.Table(FEEDBACK_TABLE)
        feedback_response = table.get_item(
            Key={
                'image_id': image_id,
                'timestamp': feedback_timestamp
            }
        )
        
        if 'Item' not in feedback_response:
            return {
                'statusCode': 404,
                'body': json.dumps({'error': 'Feedback record not found'})
            }
        
        feedback = feedback_response['Item']
        
        # Update feedback with expert decision
        table.update_item(
            Key={
                'image_id': image_id,
                'timestamp': feedback_timestamp
            },
            UpdateExpression='SET expert_action = :action, expert_class = :cls, expert_notes = :notes, expert_timestamp = :ts',
            ExpressionAttributeValues={
                ':action': action,
                ':cls': corrected_class or 'N/A',
                ':notes': notes,
                ':ts': datetime.now().isoformat()
            }
        )
        
        result = {
            'image_id': image_id,
            'action': action,
            'corrected_class': corrected_class
        }
        
        # If approved, move image to training bucket
        if action == 'approve':
            # Get s3_key from feedback or derive from image_id
            source_key = feedback.get('s3_key')
            
            if not source_key:
                # Fallback: try to find the image in uploads/
                # List objects with image_id in the name
                try:
                    response = s3.list_objects_v2(
                        Bucket=IMAGES_BUCKET,
                        Prefix='uploads/',
                        MaxKeys=100
                    )
                    
                    # Find matching image
                    for obj in response.get('Contents', []):
                        if image_id in obj['Key']:
                            source_key = obj['Key']
                            break
                except Exception as e:
                    print(f"Error finding image: {str(e)}")
            
            if source_key:
                # Copy image to training bucket
                target_key = f"approved/train/{corrected_class}/{os.path.basename(source_key)}"
                
                try:
                    s3.copy_object(
                        Bucket=TRAINING_BUCKET,
                        CopySource={'Bucket': IMAGES_BUCKET, 'Key': source_key},
                        Key=target_key
                    )
                    
                    result['training_path'] = f"s3://{TRAINING_BUCKET}/{target_key}"
                    result['status'] = 'Image approved and moved to training bucket'
                except Exception as copy_error:
                    result['status'] = f'Approved but copy failed: {str(copy_error)}'
            else:
                result['status'] = 'Approved but source image not found in S3'
        else:
            result['status'] = 'Image rejected'
        
        return {
            'statusCode': 200,
            'body': json.dumps(result)
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }