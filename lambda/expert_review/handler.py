import json
import boto3
import os
from decimal import Decimal

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
FEEDBACK_TABLE = os.environ['FEEDBACK_TABLE']


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)


def lambda_handler(event, context):
    """
    GET /expert-review - returns feedback items
    Query params:
    - filter: "needs_review" (default) | "all"
    """
    try:
        params = event.get('queryStringParameters') or {}
        filter_type = params.get('filter', 'needs_review')
        
        table = dynamodb.Table(FEEDBACK_TABLE)
        
        if filter_type == 'needs_review':
            # Only items flagged for review
            response = table.scan(
                FilterExpression='needs_expert_review = :val',
                ExpressionAttributeValues={':val': True}
            )
        else:
            # All feedback items (expert can review anything)
            response = table.scan()
        
        items = response.get('Items', [])
        
        # Sort: flagged items first, then by timestamp descending
        items.sort(key=lambda x: (
            not x.get('needs_expert_review', False),  # False first (flagged)
            -(float(x.get('timestamp', '0').replace('T', '').replace(':', '').replace('-', '').replace('.', '')[:14]))
        ))
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'count': len(items),
                'items': items
            }, cls=DecimalEncoder)
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }