#!/bin/bash

GOLDEN_BUCKET="capa-demo-virginia-acj"
TRAINING_BUCKET="capastoragestack-trainingbucketeb7bb5c9-xenilwo05ose"
IMAGES_PER_CLASS=20

classes=("Crazing" "Inclusion" "Patches" "Pitted_Surface" "Rolled_In_Scale" "Scratches")

echo "Copying $IMAGES_PER_CLASS sample images per class from golden to approved folder..."

for class in "${classes[@]}"; do
    echo "Processing $class..."
    
    # List files in golden bucket train folder
    files=$(aws s3 ls "s3://$GOLDEN_BUCKET/NEU Metal Surface Defects Data/train/$class/" | grep ".bmp" | awk '{print $4}' | head -n $IMAGES_PER_CLASS)
    
    count=0
    for file in $files; do
        aws s3 cp \
            "s3://$GOLDEN_BUCKET/NEU Metal Surface Defects Data/train/$class/$file" \
            "s3://$TRAINING_BUCKET/approved/train/$class/$file" \
            --quiet
        ((count++))
    done
    
    echo "  ✓ Copied $count images for $class"
done

echo ""
echo "Done! Verify with:"
echo "curl 'https://tujmjrsq6k.execute-api.us-east-1.amazonaws.com/prod/training-stats' | jq '.classes[] | select(.training_bucket.approved > 0) | {class: .class_name, approved: .training_bucket.approved}'"