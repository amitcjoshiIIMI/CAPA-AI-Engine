import json
import boto3
import os
from decimal import Decimal

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
    """
    try:
        http_method = event.get('httpMethod', 'GET')
        path_params = event.get('pathParameters') or {}
        query_params = event.get('queryStringParameters') or {}

        report_id = path_params.get('report_id')

        if http_method == 'GET':
            if report_id:
                # GET /reports/{report_id} - Get specific report
                return get_report(report_id)
            else:
                # GET /reports - List all reports
                return list_reports(query_params)
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
