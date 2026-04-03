import json
import boto3
import os
import base64
from datetime import datetime
from urllib.parse import unquote

s3 = boto3.client('s3', region_name='us-east-1')

IMAGES_BUCKET = os.environ['IMAGES_BUCKET']


def lambda_handler(event, context):
    """
    Images Handler

    Endpoints:
    - POST /images/upload - Upload a new image
    - GET /images/{image_id} - Get presigned URL to download image
    - GET /images - List all images
    """
    try:
        http_method = event.get('httpMethod', 'GET')
        path_params = event.get('pathParameters') or {}
        resource_path = event.get('resource', '')

        image_id = path_params.get('image_id')
        if image_id:
            image_id = unquote(image_id)  # Decode URL-encoded characters

        if http_method == 'POST' and 'upload' in resource_path:
            # POST /images/upload
            return upload_image(event)
        elif http_method == 'GET':
            if image_id:
                # GET /images/{image_id}
                return get_image(image_id)
            else:
                # GET /images
                return list_images()
        else:
            return error_response(405, f'Method {http_method} not allowed')

    except Exception as e:
        print(f"Error: {str(e)}")
        return error_response(500, str(e))


def upload_image(event):
    """Upload an image to S3"""
    # Parse request body
    if 'body' in event:
        body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
    else:
        body = event

    # Get image data (base64 encoded)
    image_data = body.get('image') or body.get('image_data')
    filename = body.get('filename', 'image.jpg')
    content_type = body.get('content_type', 'image/jpeg')

    if not image_data:
        return error_response(400, 'No image data provided. Send base64 encoded image in "image" field')

    # Generate unique image ID
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    image_id = f"img_{timestamp}_{filename}"
    s3_key = f"uploads/{image_id}"

    try:
        # Decode base64 image
        image_bytes = base64.b64decode(image_data)

        # Upload to S3
        s3.put_object(
            Bucket=IMAGES_BUCKET,
            Key=s3_key,
            Body=image_bytes,
            ContentType=content_type
        )

        return success_response({
            'image_id': image_id,
            's3_key': s3_key,
            'message': 'Image uploaded successfully'
        })

    except Exception as e:
        print(f"Upload error: {str(e)}")
        return error_response(500, f'Failed to upload image: {str(e)}')


def get_image(image_id):
    """Get a presigned URL to download an image"""
    # Try different key patterns (the image_id might be the full key or just filename)
    possible_keys = [
        f"uploads/{image_id}",
        image_id,
        f"uploads/img_{image_id}"
    ]

    # First try exact matches
    for s3_key in possible_keys:
        try:
            # Check if object exists
            s3.head_object(Bucket=IMAGES_BUCKET, Key=s3_key)

            # Generate presigned URL (valid for 1 hour)
            presigned_url = s3.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': IMAGES_BUCKET,
                    'Key': s3_key
                },
                ExpiresIn=3600  # 1 hour
            )

            return success_response({
                'image_id': image_id,
                's3_key': s3_key,
                'download_url': presigned_url,
                'expires_in_seconds': 3600
            })

        except s3.exceptions.ClientError as e:
            if e.response['Error']['Code'] != '404':
                raise
            continue

    # If no exact match, search for objects containing the image_id
    # This handles the case where inference Lambda adds timestamp prefix
    try:
        response = s3.list_objects_v2(
            Bucket=IMAGES_BUCKET,
            Prefix='uploads/',
            MaxKeys=1000
        )

        for obj in response.get('Contents', []):
            key = obj['Key']
            # Check if image_id is contained in the key
            if image_id in key:
                presigned_url = s3.generate_presigned_url(
                    'get_object',
                    Params={
                        'Bucket': IMAGES_BUCKET,
                        'Key': key
                    },
                    ExpiresIn=3600
                )

                return success_response({
                    'image_id': image_id,
                    's3_key': key,
                    'download_url': presigned_url,
                    'expires_in_seconds': 3600
                })
    except Exception as e:
        print(f"Search error: {str(e)}")

    return error_response(404, f'Image {image_id} not found')


def list_images():
    """List all images in the bucket"""
    try:
        response = s3.list_objects_v2(
            Bucket=IMAGES_BUCKET,
            Prefix='uploads/',
            MaxKeys=100
        )

        images = []
        for obj in response.get('Contents', []):
            key = obj['Key']
            # Skip the folder itself
            if key == 'uploads/':
                continue

            images.append({
                'image_id': key.replace('uploads/', ''),
                's3_key': key,
                'size_bytes': obj['Size'],
                'last_modified': obj['LastModified'].isoformat()
            })

        # Sort by last modified (newest first)
        images.sort(key=lambda x: x['last_modified'], reverse=True)

        return success_response({
            'images': images,
            'count': len(images)
        })

    except Exception as e:
        print(f"List error: {str(e)}")
        return error_response(500, f'Failed to list images: {str(e)}')


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
        })
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
