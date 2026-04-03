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
REPORTS_TABLE = os.environ.get('REPORTS_TABLE', '')
REPORTS_BUCKET = os.environ.get('REPORTS_BUCKET', '')
CLASS_REGISTRY_TABLE = os.environ.get('CLASS_REGISTRY_TABLE', '')

# Default class names (fallback if registry unavailable)
DEFAULT_CLASSES = [
    'Crazing', 'Inclusion', 'Patches',
    'Pitted_Surface', 'Rolled_In_Scale', 'Scratches'
]


def get_valid_classes():
    """Fetch valid classes from ClassRegistryTable, falling back to defaults."""
    if not CLASS_REGISTRY_TABLE:
        return DEFAULT_CLASSES
    try:
        table = dynamodb.Table(CLASS_REGISTRY_TABLE)
        response = table.scan(ProjectionExpression='class_name')
        classes = [item['class_name'] for item in response.get('Items', [])]
        return classes if classes else DEFAULT_CLASSES
    except Exception as e:
        print(f"Failed to fetch class registry: {str(e)}")
        return DEFAULT_CLASSES


def find_pending_image(image_id, predicted_class):
    """Find the pending image key in the training bucket.
    Try the specific class first, then scan all classes as fallback."""
    if predicted_class:
        key = f"pending/{predicted_class}/{image_id}"
        try:
            s3.head_object(Bucket=TRAINING_BUCKET, Key=key)
            return key
        except Exception:
            pass

    # Fallback: scan all classes under pending/
    for cls in get_valid_classes():
        key = f"pending/{cls}/{image_id}"
        try:
            s3.head_object(Bucket=TRAINING_BUCKET, Key=key)
            return key
        except Exception:
            continue
    return None


def delete_pending_image(pending_key):
    """Delete an image from the pending/ prefix in the training bucket."""
    try:
        s3.delete_object(Bucket=TRAINING_BUCKET, Key=pending_key)
        return True
    except Exception as e:
        print(f"Failed to delete pending image {pending_key}: {str(e)}")
        return False


def find_and_delete_report(image_id):
    """Find and delete the CAPA report associated with an image_id."""
    if not REPORTS_TABLE or not REPORTS_BUCKET:
        return None

    try:
        reports_table = dynamodb.Table(REPORTS_TABLE)
        # Scan for reports matching this image_id
        response = reports_table.scan(
            FilterExpression='image_id = :iid',
            ExpressionAttributeValues={':iid': image_id}
        )

        deleted_reports = []
        for item in response.get('Items', []):
            report_id = item.get('report_id')
            created_at = item.get('created_at')
            if not report_id or not created_at:
                continue

            # Delete from DynamoDB
            reports_table.delete_item(
                Key={'report_id': report_id, 'created_at': created_at}
            )

            # Delete from S3 (try common key patterns)
            for s3_key in [f"reports/{report_id}.json", f"{report_id}.json", f"reports/{report_id}"]:
                try:
                    s3.delete_object(Bucket=REPORTS_BUCKET, Key=s3_key)
                except Exception:
                    pass

            deleted_reports.append(report_id)

        return deleted_reports
    except Exception as e:
        print(f"Error deleting reports for image {image_id}: {str(e)}")
        return None


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
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'action must be "approve" or "reject"'})
            }
        
        if action == 'approve' and not corrected_class:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'corrected_class required when action=approve'})
            }
        
        valid_classes = get_valid_classes()
        if corrected_class and corrected_class not in valid_classes:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'error': f'Invalid class. Must be one of: {valid_classes}'
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
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
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

        predicted_class = feedback.get('predicted_class')

        if action == 'approve':
            # Try to find the image in training bucket pending/ first (new flow)
            pending_key = find_pending_image(image_id, predicted_class)

            if pending_key:
                # New flow: copy from pending/ to approved/train/{corrected_class}/
                target_key = f"approved/train/{corrected_class}/{image_id}"
                try:
                    s3.copy_object(
                        Bucket=TRAINING_BUCKET,
                        CopySource={'Bucket': TRAINING_BUCKET, 'Key': pending_key},
                        Key=target_key
                    )
                    delete_pending_image(pending_key)
                    result['training_path'] = f"s3://{TRAINING_BUCKET}/{target_key}"
                    result['status'] = 'Image approved and moved from pending to training bucket'
                except Exception as copy_error:
                    result['status'] = f'Approved but copy failed: {str(copy_error)}'
            else:
                # Fallback: copy from images bucket (pre-existing data)
                source_key = feedback.get('s3_key')
                if not source_key:
                    try:
                        paginator = s3.get_paginator('list_objects_v2')
                        for page in paginator.paginate(Bucket=IMAGES_BUCKET, Prefix='uploads/'):
                            for obj in page.get('Contents', []):
                                if image_id in obj['Key']:
                                    source_key = obj['Key']
                                    break
                            if source_key:
                                break
                    except Exception as e:
                        print(f"Error finding image in images bucket: {str(e)}")

                if source_key:
                    target_key = f"approved/train/{corrected_class}/{os.path.basename(source_key)}"
                    try:
                        s3.copy_object(
                            Bucket=TRAINING_BUCKET,
                            CopySource={'Bucket': IMAGES_BUCKET, 'Key': source_key},
                            Key=target_key
                        )
                        result['training_path'] = f"s3://{TRAINING_BUCKET}/{target_key}"
                        result['status'] = 'Image approved and moved to training bucket (legacy path)'
                    except Exception as copy_error:
                        result['status'] = f'Approved but copy failed: {str(copy_error)}'
                else:
                    result['status'] = 'Approved but source image not found in S3'

        else:
            # Reject flow: delete pending image + delete CAPA report
            pending_key = find_pending_image(image_id, predicted_class)
            if pending_key:
                delete_pending_image(pending_key)
                result['pending_deleted'] = True

            deleted_reports = find_and_delete_report(image_id)
            if deleted_reports:
                result['deleted_reports'] = deleted_reports

            result['status'] = 'Image rejected, pending image and reports cleaned up'
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps(result)
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