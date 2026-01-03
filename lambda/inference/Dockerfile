FROM public.ecr.aws/lambda/python:3.9

# Install PyTorch and dependencies
RUN pip install --no-cache-dir \
    "numpy<2.0" \
    torch==2.0.1 \
    torchvision==0.15.2 \
    Pillow \
    boto3

# Copy handler code
COPY handler.py ${LAMBDA_TASK_ROOT}

# Set handler
CMD ["handler.handler"]
