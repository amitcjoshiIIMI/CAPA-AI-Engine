import json
import base64
import io
import os
import boto3
from PIL import Image
import torch
import torchvision.transforms as transforms

s3 = boto3.client('s3')
MODEL_BUCKET = os.environ['MODEL_BUCKET']

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
            'image_id': body.get('image_id', 'unknown')
        }
        
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
