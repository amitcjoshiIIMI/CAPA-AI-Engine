import json
import base64
import io
import os
import boto3
from PIL import Image
import torch
import torchvision.transforms as transforms
import urllib.request
import urllib.error
from datetime import datetime

s3 = boto3.client('s3')
MODEL_BUCKET = os.environ['MODEL_BUCKET']
IMAGES_BUCKET = os.environ.get('IMAGES_BUCKET', '')
REPORT_API_URL = os.environ.get('REPORT_API_URL', 'https://6ewcd5z551.execute-api.us-east-1.amazonaws.com/prod/generate-report')

# Load model (global to reuse across invocations)
model = None
class_names = None

def load_model():
    global model, class_names
    if model is None:
        # Download model
        s3.download_file(MODEL_BUCKET, 'model.pth', '/tmp/model.pth')
        s3.download_file(MODEL_BUCKET, 'model_metadata.json', '/tmp/model_metadata.json')
        
        # Load metadata
        with open('/tmp/model_metadata.json', 'r') as f:
            metadata = json.load(f)
            class_names = metadata['class_names']
        
        # Load model
        from torchvision.models import resnet18
        model = resnet18(num_classes=len(class_names))
        model.load_state_dict(torch.load('/tmp/model.pth', map_location='cpu'))
        model.eval()

def save_image_to_s3(image_bytes, image_id):
    """Save uploaded image to S3 for later expert review"""
    if not IMAGES_BUCKET:
        return None
    
    try:
        # Use timestamp to avoid collisions
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        s3_key = f"uploads/{timestamp}_{image_id}"
        
        s3.put_object(
            Bucket=IMAGES_BUCKET,
            Key=s3_key,
            Body=image_bytes
        )
        return s3_key
    except Exception as e:
        print(f"Failed to save image to S3: {str(e)}")
        return None

def handler(event, context):
    try:
        load_model()
        
        # Parse body (handle both direct invoke and API Gateway format)
        if 'body' in event:
            if isinstance(event['body'], str):
                body = json.loads(event['body'])
            else:
                body = event['body']
        else:
            body = event
        
        # Support both 'image' and 'image_data' field names
        image_b64 = body.get('image') or body.get('image_data')
        
        if not image_b64:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'No image provided (expected "image" or "image_data" field)'})
            }
        
        # Decode image
        image_bytes = base64.b64decode(image_b64)
        # Save to S3 for expert review
        s3_key = save_image_to_s3(image_bytes, body.get('image_id', 'unknown'))
        image = Image.open(io.BytesIO(image_bytes)).convert('RGB')
        
        # Preprocess
        transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
        ])
        img_tensor = transform(image).unsqueeze(0)
        
        # Inference
        with torch.no_grad():
            outputs = model(img_tensor)
            probabilities = torch.nn.functional.softmax(outputs, dim=1)
            confidence, predicted = torch.max(probabilities, 1)
        
        result = {
            'predicted_class': class_names[predicted.item()],
            'confidence': float(confidence.item()),
            'image_id': body.get('image_id', 'unknown'),
            's3_key': s3_key  # Add this line
        }
        
        # Auto-trigger report generation if confidence > 0.95
        report_id = None
        if confidence.item() > 0.95:
            try:
                report_payload = json.dumps({
                    'image_id': result['image_id'],
                    'failure_mode': result['predicted_class'],
                    'confidence': str(result['confidence'])
                }).encode('utf-8')
                
                req = urllib.request.Request(
                    REPORT_API_URL,
                    data=report_payload,
                    headers={'Content-Type': 'application/json'}
                )
                
                with urllib.request.urlopen(req, timeout=30) as response:
                    report_data = json.loads(response.read().decode('utf-8'))
                    report_id = report_data.get('report_id')
                    result['report_generated'] = True
                    result['report_id'] = report_id
            except Exception as report_error:
                # Don't fail the whole request if report generation fails
                result['report_generated'] = False
                result['report_error'] = str(report_error)
        else:
            result['report_generated'] = False
            result['report_reason'] = 'Confidence below threshold (0.95)'
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps(result)
        }
    
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
