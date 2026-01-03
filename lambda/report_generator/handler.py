import json
import boto3
import os
from datetime import datetime
from decimal import Decimal

# Force region for all boto3 clients
REGION = 'us-east-1'
bedrock = boto3.client('bedrock-runtime', region_name=REGION)
dynamodb = boto3.resource('dynamodb', region_name=REGION)
s3 = boto3.client('s3', region_name=REGION)

REPORTS_TABLE = os.environ['REPORTS_TABLE']
REPORTS_BUCKET = os.environ['REPORTS_BUCKET']
MODEL_ID = "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-5-sonnet-20240620-v1:0"


def lambda_handler(event, context):
    """
    Expected input:
    {
        "image_id": "Cr_1.bmp",
        "failure_mode": "Crazing",
        "confidence": "0.99"
    }
    """
    try:
        body = json.loads(event['body']) if 'body' in event else event
        
        image_id = body['image_id']
        failure_mode = body['failure_mode']
        confidence = body.get('confidence', '0.0')
        
        # Step 1: Retrieve similar reports (RAG - simplified for now)
        similar_reports = get_similar_reports(failure_mode)
        
        # Step 2: Generate CAPA report using Bedrock
        report_data = generate_capa_report(failure_mode, similar_reports)
        
        # Step 3: Save to DynamoDB and S3
        report_id = f"CAPA_{image_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        full_report = {
            "report_id": report_id,
            "created_at": datetime.now().isoformat(),
            "image_id": image_id,
            "failure_mode": failure_mode,
            "confidence": confidence,
            "is_seed": False,
            **report_data
        }
        
        # DynamoDB
        table = dynamodb.Table(REPORTS_TABLE)
        table.put_item(Item=json.loads(json.dumps(full_report), parse_float=Decimal))
        
        # S3
        s3.put_object(
            Bucket=REPORTS_BUCKET,
            Key=f"reports/{report_id}.json",
            Body=json.dumps(full_report, indent=2)
        )
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'report_id': report_id,
                'report': full_report
            })
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }


def get_similar_reports(failure_mode):
    """Retrieve seed report for this failure mode (simplified RAG)"""
    table = dynamodb.Table(REPORTS_TABLE)
    
    # Query for seed reports with this failure mode
    response = table.scan(
        FilterExpression='failure_mode = :fm AND is_seed = :seed',
        ExpressionAttributeValues={
            ':fm': failure_mode,
            ':seed': True
        },
        Limit=1
    )
    
    return response.get('Items', [])


def generate_capa_report(failure_mode, similar_reports):
    """Call Bedrock Claude to generate CAPA report"""
    
    # Build context from similar reports
    context = ""
    if similar_reports:
        context = f"\n\nHere is a reference CAPA report for {failure_mode}:\n"
        context += json.dumps(similar_reports[0], indent=2, default=str)
    
    prompt = f"""You are a quality engineering expert. Generate a detailed CAPA (Corrective and Preventive Action) report for a {failure_mode} defect.

{context}

Generate a comprehensive report with the following structure (return ONLY valid JSON):

{{
  "failure_mode": "{failure_mode}",
  "five_whys": {{
    "why_1": "...",
    "why_2": "...",
    "why_3": "...",
    "why_4": "...",
    "why_5": "..."
  }},
  "fishbone": {{
    "man": "...",
    "machine": "...",
    "material": "...",
    "method": "...",
    "measurement": "...",
    "environment": "..."
  }},
  "8d_report": {{
    "d1_team": "...",
    "d2_problem": "...",
    "d3_interim": "...",
    "d4_root_cause": "...",
    "d5_corrective": "...",
    "d6_implementation": "...",
    "d7_prevention": "...",
    "d8_recognition": "..."
  }}
}}

Generate realistic, detailed content for each field. Return ONLY the JSON object, no additional text."""

    bedrock_client = boto3.client('bedrock-runtime', region_name='us-east-1')
    response = bedrock_client.invoke_model(
        modelId=MODEL_ID,
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4000,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        })
    )
    
    result = json.loads(response['body'].read())
    report_text = result['content'][0]['text']
    
    # Parse JSON from response
    return json.loads(report_text)