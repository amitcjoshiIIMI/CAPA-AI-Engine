import json
import boto3
import os
from collections import defaultdict

s3 = boto3.client('s3', region_name='us-east-1')
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

TRAINING_BUCKET = os.environ['TRAINING_BUCKET']
CLASS_REGISTRY_TABLE = os.environ['CLASS_REGISTRY_TABLE']


def count_images_in_folder(bucket, prefix):
    """Count image files in an S3 prefix"""
    try:
        paginator = s3.get_paginator('list_objects_v2')
        count = 0
        
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get('Contents', []):
                key = obj['Key']
                # Count actual image files (not .readme)
                if key.lower().endswith(('.bmp', '.png', '.jpg', '.jpeg', '.webp', '.gif', '.tiff', '.tif')) and not key.endswith('/.readme'):
                    count += 1
        
        return count
    except Exception as e:
        print(f"Error counting in {bucket}/{prefix}: {str(e)}")
        return 0


def lambda_handler(event, context):
    """
    GET /training-stats
    Returns image counts per class across all storage locations
    """
    try:
        # Get all classes from registry
        table = dynamodb.Table(CLASS_REGISTRY_TABLE)
        registry_response = table.scan()
        classes = registry_response.get('Items', [])
        
        stats = []
        
        for cls in classes:
            class_name = cls['class_name']
            
            # Count in training bucket
            pending_count = count_images_in_folder(TRAINING_BUCKET, f"pending/{class_name}/")
            approved_count = count_images_in_folder(TRAINING_BUCKET, f"approved/train/{class_name}/")
            
            # Count in golden dataset (same bucket, golden/ prefix)
            golden_train = count_images_in_folder(TRAINING_BUCKET, f"golden/train/{class_name}/")
            golden_valid = count_images_in_folder(TRAINING_BUCKET, f"golden/valid/{class_name}/")
            golden_test = count_images_in_folder(TRAINING_BUCKET, f"golden/test/{class_name}/")
            
            class_stat = {
                'class_name': class_name,
                'description': cls.get('description', ''),
                'is_original': cls.get('is_original', False),
                'training_bucket': {
                    'pending': pending_count,
                    'approved': approved_count,
                    'total': pending_count + approved_count
                },
                'golden_dataset': {
                    'train': golden_train,
                    'valid': golden_valid,
                    'test': golden_test,
                    'total': golden_train + golden_valid + golden_test
                },
                'grand_total': pending_count + approved_count + golden_train + golden_valid + golden_test
            }
            
            stats.append(class_stat)
        
        # Sort by total images descending
        stats.sort(key=lambda x: x['grand_total'], reverse=True)
        
        # Calculate totals
        total_pending = sum(s['training_bucket']['pending'] for s in stats)
        total_approved = sum(s['training_bucket']['approved'] for s in stats)
        total_golden = sum(s['golden_dataset']['total'] for s in stats)
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'summary': {
                    'total_classes': len(stats),
                    'training_bucket': {
                        'pending': total_pending,
                        'approved': total_approved,
                        'total': total_pending + total_approved
                    },
                    'golden_dataset': {
                        'total': total_golden
                    },
                    'grand_total': total_pending + total_approved + total_golden
                },
                'classes': stats
            }, default=str)
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