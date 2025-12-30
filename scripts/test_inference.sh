#!/bin/bash

# Get API URL from CloudFormation output
API_URL=$(aws cloudformation describe-stacks \
  --stack-name CapaInferenceStack \
  --query 'Stacks[0].Outputs[?OutputKey==`InferenceUrl`].OutputValue' \
  --output text)

echo "API URL: $API_URL"

# Path to test image (quote it to handle spaces)
IMAGE_PATH="data/NEU Metal Surface Defects Data/test/Crazing/Cr_1.bmp"

# Check if file exists
if [ ! -f "$IMAGE_PATH" ]; then
    echo "Error: Image file not found: $IMAGE_PATH"
    exit 1
fi

echo "Testing with image: $IMAGE_PATH"

# Encode image to base64
IMAGE_B64=$(base64 -i "$IMAGE_PATH")

# Make API request
curl -X POST "$API_URL" \
  -H "Content-Type: application/json" \
  -d "{
    \"image_data\": \"$IMAGE_B64\",
    \"image_id\": \"test-001\"
  }" | jq
