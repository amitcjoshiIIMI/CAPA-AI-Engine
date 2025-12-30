FROM public.ecr.aws/lambda/python:3.11

RUN yum install -y gcc gcc-c++ make cmake libgomp

COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r requirements.txt

RUN python -c "import numpy; print('NumPy OK:', numpy.__version__)" && \
    python -c "import torch; print('PyTorch OK:', torch.__version__)"

COPY handler.py ${LAMBDA_TASK_ROOT}/

CMD ["handler.handler"]
