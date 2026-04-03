import json
import boto3
import os
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import unquote

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
s3 = boto3.client('s3', region_name='us-east-1')

REPORTS_TABLE = os.environ['REPORTS_TABLE']
REPORTS_BUCKET = os.environ['REPORTS_BUCKET']


class DecimalEncoder(json.JSONEncoder):
    """Custom JSON encoder for DynamoDB Decimal values"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)


def lambda_handler(event, context):
    """
    Reports CRUD Handler

    Endpoints:
    - GET /reports - List all reports
    - GET /reports/{report_id} - Get specific report
    - PUT /reports/{report_id} - Update report fields
    """
    try:
        http_method = event.get('httpMethod', 'GET')
        path_params = event.get('pathParameters') or {}
        query_params = event.get('queryStringParameters') or {}

        report_id = path_params.get('report_id')
        if report_id:
            report_id = unquote(report_id)  # Decode URL-encoded characters

        if http_method == 'GET':
            if report_id:
                # GET /reports/{report_id} - Get specific report
                return get_report(report_id)
            else:
                # GET /reports - List all reports
                return list_reports(query_params)
        elif http_method == 'PUT':
            if report_id:
                body = json.loads(event.get('body') or '{}')
                return update_report(report_id, body)
            else:
                return error_response(400, 'report_id is required for PUT')
        else:
            return error_response(405, f'Method {http_method} not allowed')

    except Exception as e:
        print(f"Error: {str(e)}")
        return error_response(500, str(e))


def get_report(report_id):
    """Get a specific report by ID"""
    table = dynamodb.Table(REPORTS_TABLE)

    # Query by partition key (report_id)
    # Since we have a sort key (created_at), we need to query
    response = table.query(
        KeyConditionExpression='report_id = :rid',
        ExpressionAttributeValues={':rid': report_id},
        Limit=1
    )

    items = response.get('Items', [])

    if not items:
        return error_response(404, f'Report {report_id} not found')

    report = items[0]

    return success_response(report)


def list_reports(query_params):
    """List all reports with optional filters"""
    table = dynamodb.Table(REPORTS_TABLE)

    # Get optional filters
    failure_mode = query_params.get('failure_mode')
    limit = int(query_params.get('limit', 50))

    # Build scan parameters
    scan_kwargs = {'Limit': min(limit, 100)}  # Cap at 100 for safety

    if failure_mode:
        scan_kwargs['FilterExpression'] = 'failure_mode = :fm'
        scan_kwargs['ExpressionAttributeValues'] = {':fm': failure_mode}

    response = table.scan(**scan_kwargs)
    items = response.get('Items', [])

    # Sort by created_at descending (newest first)
    items.sort(key=lambda x: x.get('created_at', ''), reverse=True)

    # Return summary for list view (not full report details)
    summaries = []
    for item in items:
        summaries.append({
            'report_id': item.get('report_id'),
            'failure_mode': item.get('failure_mode'),
            'image_id': item.get('image_id'),
            'confidence': item.get('confidence'),
            'created_at': item.get('created_at'),
            'is_seed': item.get('is_seed', False)
        })

    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps({
            'success': True,
            'data': summaries,
            'count': len(summaries)
        }, cls=DecimalEncoder)
    }


def update_report(report_id, body):
    """Update editable fields of a report (five_whys, fishbone, 8d_report)"""
    ALLOWED_FIELDS = {'five_whys', 'fishbone', '8d_report'}

    updates = {k: v for k, v in body.items() if k in ALLOWED_FIELDS}
    if not updates:
        return error_response(400, 'No valid fields to update. Allowed: five_whys, fishbone, 8d_report')

    table = dynamodb.Table(REPORTS_TABLE)

    # Query to get the sort key (created_at)
    response = table.query(
        KeyConditionExpression='report_id = :rid',
        ExpressionAttributeValues={':rid': report_id},
        Limit=1
    )
    items = response.get('Items', [])
    if not items:
        return error_response(404, f'Report {report_id} not found')

    created_at = items[0]['created_at']
    now = datetime.now(timezone.utc).isoformat()

    # Build update expression
    expr_parts = []
    expr_names = {}
    expr_values = {':updated_at': now}

    for field, value in updates.items():
        safe_name = field.replace('8d_report', 'eight_d_report')
        placeholder = f'#{safe_name}'
        expr_names[placeholder] = field
        expr_values[f':{safe_name}'] = value
        expr_parts.append(f'{placeholder} = :{safe_name}')

    expr_parts.append('#updated_at = :updated_at')
    expr_names['#updated_at'] = 'updated_at'

    update_expression = 'SET ' + ', '.join(expr_parts)

    table.update_item(
        Key={'report_id': report_id, 'created_at': created_at},
        UpdateExpression=update_expression,
        ExpressionAttributeNames=expr_names,
        ExpressionAttributeValues=expr_values,
    )

    # Update S3 backup
    try:
        s3_key = f"reports/{report_id}.json"
        existing = s3.get_object(Bucket=REPORTS_BUCKET, Key=s3_key)
        report_data = json.loads(existing['Body'].read().decode('utf-8'))
        report_data.update(updates)
        report_data['updated_at'] = now
        s3.put_object(
            Bucket=REPORTS_BUCKET,
            Key=s3_key,
            Body=json.dumps(report_data, cls=DecimalEncoder),
            ContentType='application/json',
        )
    except Exception as e:
        # S3 backup is best-effort; DynamoDB is source of truth
        print(f"Warning: Failed to update S3 backup for {report_id}: {e}")

    # Return updated report
    return get_report(report_id)


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
