# CAPA-AI-Engine

A comprehensive AWS-based system for detecting metal surface defects using computer vision and generating automated CAPA (Corrective and Preventive Action) reports powered by AI.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [API Endpoints](#api-endpoints)
- [Database Schemas](#database-schemas)
- [Machine Learning Model](#machine-learning-model)
- [Key Functions](#key-functions)
- [Use Cases](#use-cases)
- [AWS Configuration](#aws-configuration)
- [Installation & Deployment](#installation--deployment)
- [Usage](#usage)
- [Functional Requirements](#functional-requirements)
- [Non-Functional Requirements](#non-functional-requirements)
- [Possible Improvements](#possible-improvements)
- [Cost Considerations](#cost-considerations)

---

## Overview

CAPA-AI-Engine is a serverless application that combines deep learning-based defect detection with LLM-powered root cause analysis. The system:

1. **Detects** 6 types of metal surface defects using a ResNet-18 model
2. **Generates** detailed CAPA reports using Claude 3.5 Sonnet (AWS Bedrock)
3. **Collects** user feedback to improve model predictions
4. **Queues** flagged predictions for expert review

### Supported Defect Types

| Defect | Description |
|--------|-------------|
| Crazing | Network of fine cracks from thermal stress |
| Inclusion | Foreign particles embedded in metal surface |
| Patches | Uneven coating or surface irregularities |
| Pitted_Surface | Small holes/pits from corrosion or acid exposure |
| Rolled_In_Scale | Oxide scale pressed into surface during rolling |
| Scratches | Linear surface damage from mechanical contact |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              User Request                                │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           AWS API Gateway                                │
├─────────────┬─────────────┬─────────────────────┬───────────────────────┤
│   POST /    │ POST        │   POST /feedback    │  GET /expert-review   │
│ (Inference) │ /generate   │                     │                       │
│             │ -report     │                     │                       │
└──────┬──────┴──────┬──────┴──────────┬──────────┴───────────┬───────────┘
       │             │                 │                      │
       ▼             ▼                 ▼                      ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐
│   Lambda     │ │   Lambda     │ │   Lambda     │ │       Lambda         │
│  Inference   │ │   Report     │ │  Feedback    │ │    Expert Review     │
│  (Docker)    │ │  Generator   │ │              │ │                      │
└──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └──────────┬───────────┘
       │                │                │                    │
       │                ▼                │                    │
       │         ┌──────────────┐        │                    │
       │         │ AWS Bedrock  │        │                    │
       │         │Claude 3.5    │        │                    │
       │         │ Sonnet       │        │                    │
       │         └──────────────┘        │                    │
       │                                 │                    │
       ▼                ▼                ▼                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                              AWS Storage                                 │
├───────────────────┬───────────────────┬─────────────────────────────────┤
│        S3         │       S3          │            DynamoDB             │
│   (Images +       │    (Reports)      │   (Feedback + Reports +         │
│    Models)        │                   │    Inference Data)              │
└───────────────────┴───────────────────┴─────────────────────────────────┘
```

### AWS CDK Stacks

The system is deployed as 5 independent CloudFormation stacks:

| Stack | Purpose | Resources |
|-------|---------|-----------|
| `StorageStack` | Central storage layer | S3 buckets, DynamoDB tables |
| `CapaInferenceStack` | Defect detection | Lambda (Docker), API Gateway |
| `ReportGeneratorStack` | CAPA report generation | Lambda, API Gateway, Bedrock access |
| `FeedbackStack` | User feedback collection | Lambda, API Gateway |
| `ExpertReviewStack` | Review queue management | Lambda, API Gateway |

---

## Features

### 1. Automatic Report Generation
- Inference confidence > 0.95 triggers report generation automatically
- Non-blocking async invocation (doesn't delay inference response)

### 2. User Feedback Loop
- Users can agree/disagree with predictions
- Disagreement captures corrected class for model retraining
- Low confidence (< 0.90) auto-flagged for expert review
- Disagreements auto-flagged for expert review

### 3. Expert Review Queue
- Central queue for suspicious predictions
- Sortable by review status and timestamp
- Enables expert validation and corrections

### 4. RAG-Powered Report Generation
- Retrieves seed reports for specific failure modes
- Claude generates customized CAPA analysis using context
- Output includes: 5-Why, Fishbone (6M), and 8D report structure

### 5. Multi-Stage Validation
1. Automated ML detection
2. User-level validation
3. Expert review for flagged items
4. AI-generated reports for documentation

---

## Tech Stack

### Infrastructure
- **AWS CDK** - Infrastructure as Code
- **AWS Lambda** - Serverless compute
- **AWS API Gateway** - REST API management
- **AWS DynamoDB** - NoSQL database
- **Amazon S3** - Object storage
- **AWS Bedrock** - LLM inference (Claude 3.5 Sonnet)

### Machine Learning
- **PyTorch 2.1.0** - Deep learning framework
- **TorchVision 0.16.0** - Model zoo and transforms
- **ResNet-18** - Pretrained CNN architecture
- **Pillow 10.1.0** - Image processing

### Runtime
- **Python 3.9** - Inference Lambda (Docker)
- **Python 3.11** - Other Lambda functions
- **Docker** - Container images for Lambda

---

## Project Structure

```
CAPA-AI-Engine/
├── cdk/
│   ├── app.py                          # CDK app entry point
│   ├── requirements.txt                # CDK dependencies
│   └── stacks/
│       ├── __init__.py
│       ├── storage_stack.py            # S3, DynamoDB resources
│       ├── inference_stack.py          # Inference Lambda + API
│       ├── report_generator_stack.py   # Report Lambda + API
│       ├── feedback_stack.py           # Feedback Lambda + API
│       └── expert_review_stack.py      # Expert Review Lambda + API
├── lambda/
│   ├── inference/
│   │   ├── handler.py                  # Defect detection logic
│   │   ├── requirements.txt            # ML dependencies
│   │   └── Dockerfile                  # Container image spec
│   ├── report_generator/
│   │   ├── handler.py                  # CAPA report generation
│   │   └── requirements.txt
│   ├── feedback/
│   │   ├── handler.py                  # Feedback collection
│   │   └── requirements.txt
│   └── expert_review/
│       └── handler.py                  # Review queue retrieval
├── models/
│   ├── resnet18_capa.pth               # Trained model weights
│   └── model_metadata.json             # Model configuration
├── scripts/
│   ├── train_model.py                  # Model training script
│   └── test_inference.sh               # Integration test
├── seed_data/
│   └── synthetic_reports.py            # Seed report uploader
├── data/
│   └── NEU Metal Surface Defects Data/ # Training dataset
│       ├── train/
│       ├── valid/
│       └── test/
├── cdk.json                            # CDK configuration
├── requirements.txt                    # Root dependencies
└── README.md
```

---

## API Endpoints

### 1. Inference API

**Endpoint:** `POST /`
**Stack:** `CapaInferenceStack`
**Purpose:** Run defect detection on metal surface images

**Request:**
```json
{
  "image": "<base64-encoded-image>",
  "image_id": "test-001"
}
```

**Response:**
```json
{
  "statusCode": 200,
  "body": {
    "predicted_class": "Crazing",
    "confidence": 0.98,
    "image_id": "test-001",
    "report_generated": true,
    "report_id": "CAPA_test-001_20250107_120000"
  }
}
```

**Behavior:**
- Downloads and caches ResNet-18 model from S3
- Preprocesses image (resize to 224x224, ImageNet normalization)
- Runs inference and returns prediction
- Auto-triggers report generation if confidence > 0.95

---

### 2. Report Generator API

**Endpoint:** `POST /generate-report`
**Stack:** `ReportGeneratorStack`
**Purpose:** Generate AI-powered CAPA reports

**Request:**
```json
{
  "image_id": "Cr_1.bmp",
  "failure_mode": "Crazing",
  "confidence": "0.99"
}
```

**Response:**
```json
{
  "statusCode": 200,
  "body": {
    "message": "CAPA report generated successfully",
    "report_id": "CAPA_Cr_1.bmp_20250107_120000",
    "created_at": "2025-01-07T12:00:00.000000",
    "image_id": "Cr_1.bmp",
    "failure_mode": "Crazing"
  }
}
```

**Generated Report Structure:**
```json
{
  "report_id": "CAPA_...",
  "five_whys": {
    "why_1": "Surface cracking observed",
    "why_2": "Thermal stress during cooling",
    "why_3": "Cooling rate too rapid",
    "why_4": "Temperature controller malfunction",
    "why_5": "Missed preventive maintenance"
  },
  "fishbone": {
    "man": "Operator oversight",
    "machine": "Temperature controller failure",
    "material": "Material brittleness",
    "method": "Cooling procedure inadequate",
    "measurement": "Temperature monitoring gaps",
    "environment": "Ambient temperature fluctuations"
  },
  "8d_report": {
    "d1_team": "Quality team composition",
    "d2_problem": "Problem statement",
    "d3_interim": "Containment actions",
    "d4_root_cause": "Root cause analysis",
    "d5_corrective": "Corrective actions",
    "d6_implementation": "Implementation plan",
    "d7_prevention": "Preventive measures",
    "d8_recognition": "Team recognition"
  }
}
```

---

### 3. Feedback API

**Endpoint:** `POST /feedback`
**Stack:** `FeedbackStack`
**Purpose:** Capture user validation feedback

**Request:**
```json
{
  "image_id": "Cr_1.bmp",
  "predicted_class": "Crazing",
  "user_action": "agree",
  "confidence": "0.98",
  "user_id": "user123"
}
```

**Request (disagreement):**
```json
{
  "image_id": "Cr_1.bmp",
  "predicted_class": "Crazing",
  "user_action": "disagree",
  "corrected_class": "Scratches",
  "confidence": "0.75",
  "user_id": "user123"
}
```

**Response:**
```json
{
  "statusCode": 200,
  "body": {
    "message": "Feedback recorded successfully",
    "feedback_id": "Cr_1.bmp#2025-01-07T12:00:00.000000",
    "needs_expert_review": true
  }
}
```

**Auto-Flagging Rules:**
- `user_action == "disagree"` → `needs_expert_review = true`
- `confidence < 0.90` → `needs_expert_review = true`

---

### 4. Expert Review API

**Endpoint:** `GET /expert-review`
**Stack:** `ExpertReviewStack`
**Purpose:** Retrieve items needing expert validation

**Query Parameters:**
- `filter=needs_review` (default) - Only flagged items
- `filter=all` - All feedback items

**Response:**
```json
{
  "statusCode": 200,
  "body": {
    "count": 5,
    "items": [
      {
        "image_id": "Cr_1.bmp",
        "timestamp": "2025-01-07T12:00:00.000000",
        "predicted_class": "Crazing",
        "user_action": "disagree",
        "corrected_class": "Scratches",
        "confidence": "0.75",
        "needs_expert_review": true,
        "review_reason": "User disagreement"
      }
    ]
  }
}
```

---

## Database Schemas

### FeedbackTable (DynamoDB)

| Attribute | Type | Description |
|-----------|------|-------------|
| `image_id` | String (PK) | Image identifier |
| `timestamp` | String (SK) | ISO 8601 timestamp |
| `predicted_class` | String | Model prediction |
| `user_action` | String | "agree" or "disagree" |
| `corrected_class` | String | User's correction (if disagreed) |
| `confidence` | String | Model confidence score |
| `user_id` | String | User identifier |
| `needs_expert_review` | Boolean | Flag for expert review |
| `review_reason` | String | Reason for flagging |

### ReportsTable (DynamoDB)

| Attribute | Type | Description |
|-----------|------|-------------|
| `report_id` | String (PK) | Unique report identifier |
| `created_at` | String (SK) | ISO 8601 timestamp |
| `image_id` | String | Associated image |
| `failure_mode` | String | Defect type |
| `confidence` | String | Inference confidence |
| `is_seed` | Boolean | Seed report flag |
| `five_whys` | Map | 5-Why analysis |
| `fishbone` | Map | Fishbone diagram (6M) |
| `8d_report` | Map | 8D report structure |

### InferenceDataTable (DynamoDB)

| Attribute | Type | Description |
|-----------|------|-------------|
| `image_id` | String (PK) | Image identifier |
| `inference_timestamp` | String (SK) | ISO 8601 timestamp |
| `predicted_class` | String | Model prediction |
| `confidence` | Number | Confidence score |
| `model_version` | String | Model version used |
| `report_id` | String | Associated report ID |

---

## Machine Learning Model

### Model Configuration

```json
{
  "architecture": "ResNet-18 (pretrained on ImageNet)",
  "input_size": [224, 224],
  "num_classes": 6,
  "class_names": [
    "Crazing",
    "Inclusion",
    "Patches",
    "Pitted_Surface",
    "Rolled_In_Scale",
    "Scratches"
  ],
  "normalization": {
    "mean": [0.485, 0.456, 0.406],
    "std": [0.229, 0.224, 0.225]
  }
}
```

### Training Details

- **Dataset:** NEU Metal Surface Defects Dataset
- **Architecture:** ResNet-18 with modified final layer
- **Optimizer:** Adam (lr=0.001)
- **Loss Function:** CrossEntropyLoss
- **Data Augmentation:** RandomCrop, HorizontalFlip
- **Splits:** Train/Validation/Test

### Model Files

- `models/resnet18_capa.pth` - Trained weights
- `models/model_metadata.json` - Model configuration

---

## Key Functions

### Inference Handler (`lambda/inference/handler.py`)

```python
load_model()
    # Downloads model from S3 (cached in memory)
    # Loads model_metadata.json
    # Initializes ResNet-18 with 6 output classes

handler(event, context)
    # Parses base64 image from request
    # Preprocesses: resize, normalize
    # Runs inference
    # Auto-triggers report if confidence > 0.95
    # Returns prediction + report_id
```

### Report Generator (`lambda/report_generator/handler.py`)

```python
get_similar_reports(failure_mode)
    # Queries DynamoDB for seed reports
    # Returns reference reports for RAG

generate_capa_report(failure_mode, similar_reports)
    # Builds prompt with seed report context
    # Calls Claude 3.5 Sonnet via Bedrock
    # Parses JSON response (5-whys, fishbone, 8D)

lambda_handler(event, context)
    # Retrieves similar reports
    # Generates CAPA report via Claude
    # Saves to DynamoDB + S3
    # Returns report_id
```

### Feedback Handler (`lambda/feedback/handler.py`)

```python
lambda_handler(event, context)
    # Validates user_action (agree/disagree)
    # If disagree: requires corrected_class
    # Auto-flags if confidence < 0.90
    # Auto-flags if user disagreed
    # Saves to DynamoDB
    # Returns feedback_id + needs_expert_review
```

### Expert Review Handler (`lambda/expert_review/handler.py`)

```python
lambda_handler(event, context)
    # Parses filter parameter
    # Queries FeedbackTable
    # Sorts: flagged items first, then by timestamp
    # Returns paginated results
```

---

## Use Cases

### 1. Quality Control in Manufacturing
- Real-time defect detection on production lines
- Automatic documentation of quality issues
- Standardized CAPA report generation

### 2. Root Cause Analysis Automation
- AI-powered 5-Why analysis
- Fishbone diagram generation (6M model)
- 8D problem-solving methodology

### 3. Training Data Collection
- User feedback loop improves model accuracy
- Expert validation ensures data quality
- Continuous learning from corrections

### 4. Compliance Documentation
- Automated report generation for audits
- Standardized CAPA format
- Historical tracking of defects and resolutions

### 5. Expert Support System
- Flagged items queue for expert review
- Low-confidence predictions highlighted
- User disagreements captured for analysis

---

## AWS Configuration

### Account Details

| Setting | Value |
|---------|-------|
| **Account ID** | `<YOUR_AWS_ACCOUNT_ID>` |
| **Region** | `us-east-1` |
| **Console URL** | `https://<YOUR_AWS_ACCOUNT_ID>.signin.aws.amazon.com/console` |

### CLI Configuration

To access the deployed resources via AWS CLI:

```bash
aws configure
# Enter:
#   AWS Access Key ID: [Your access key]
#   AWS Secret Access Key: [Your secret key]
#   Default region: us-east-1
#   Output format: json
```

Verify access:
```bash
aws sts get-caller-identity
```

---

## Installation & Deployment

### Already Deployed?

If the system is already deployed on your AWS account, you can skip the deployment steps below. You only need to redeploy when:
- Modifying CDK stack configurations
- Updating Lambda function code
- Changing infrastructure settings

### Deployed API Endpoints

| API | URL |
|-----|-----|
| **Inference** | `https://<api-id>.execute-api.us-east-1.amazonaws.com/prod/` |
| **Report Generator** | `https://<api-id>.execute-api.us-east-1.amazonaws.com/prod/` |
| **Feedback** | `https://<api-id>.execute-api.us-east-1.amazonaws.com/prod/` |
| **Expert Review** | `https://<api-id>.execute-api.us-east-1.amazonaws.com/prod/` |

### Deployed Storage Resources

| Resource | Name |
|----------|------|
| **Models Bucket** | `capastoragestack-modelsbucket-<unique-id>` |
| **Reports Bucket** | `capastoragestack-reportsbucket-<unique-id>` |
| **Feedback Table** | `CapaStorageStack-FeedbackTable-<unique-id>` |
| **Reports Table** | `CapaStorageStack-ReportsTable-<unique-id>` |
| **Inference Table** | `CapaStorageStack-InferenceDataTable-<unique-id>` |

To get your actual endpoints after deployment:
```bash
aws cloudformation describe-stacks --query "Stacks[?contains(StackName, 'Capa')].Outputs"
```

---

### First-Time Deployment

#### Prerequisites

- AWS CLI configured with appropriate credentials
- Node.js (for AWS CDK CLI)
- Python 3.9+
- Docker (for inference Lambda)

#### Setup

```bash
# Clone the repository
git clone <repository-url>
cd CAPA-AI-Engine

# Install AWS CDK CLI
npm install -g aws-cdk

# Install Python dependencies
pip install -r requirements.txt
cd cdk && pip install -r requirements.txt

# Bootstrap CDK (first time only)
cdk bootstrap

# Synthesize CloudFormation templates
cdk synth

# Deploy all stacks
cdk deploy --all
```

---

### Redeploying After Changes

```bash
# After modifying Lambda code or CDK stacks
cd cdk
cdk diff          # Preview changes
cdk deploy --all  # Apply changes
```

### Stack Deployment Order

The CDK handles dependencies automatically, but stacks are deployed in this order:
1. `StorageStack` (dependencies for other stacks)
2. `CapaInferenceStack`
3. `ReportGeneratorStack`
4. `FeedbackStack`
5. `ExpertReviewStack`

### Upload Model to S3

```bash
# After deployment, upload the model
aws s3 cp models/resnet18_capa.pth s3://<model-bucket-name>/model.pth
aws s3 cp models/model_metadata.json s3://<model-bucket-name>/model_metadata.json
```

### Seed Data Upload

```bash
# Upload seed reports for RAG
cd seed_data
python synthetic_reports.py
```

---

## Usage

### Running Inference

```bash
# Encode image to base64
IMAGE_BASE64=$(base64 -i path/to/image.bmp)

# Call inference API
curl -X POST https://<inference-api-id>.execute-api.us-east-1.amazonaws.com/prod/ \
  -H "Content-Type: application/json" \
  -d "{\"image\": \"$IMAGE_BASE64\", \"image_id\": \"test-001\"}"
```

### Submitting Feedback

```bash
# Agree with prediction
curl -X POST https://<feedback-api-id>.execute-api.us-east-1.amazonaws.com/prod/ \
  -H "Content-Type: application/json" \
  -d '{
    "image_id": "test-001",
    "predicted_class": "Crazing",
    "user_action": "agree",
    "confidence": "0.98",
    "user_id": "user123"
  }'

# Disagree with prediction
curl -X POST https://<feedback-api-id>.execute-api.us-east-1.amazonaws.com/prod/ \
  -H "Content-Type: application/json" \
  -d '{
    "image_id": "test-001",
    "predicted_class": "Crazing",
    "user_action": "disagree",
    "corrected_class": "Scratches",
    "confidence": "0.75",
    "user_id": "user123"
  }'
```

### Retrieving Expert Review Queue

```bash
# Get flagged items only
curl "https://<expert-review-api-id>.execute-api.us-east-1.amazonaws.com/prod/?filter=needs_review"

# Get all feedback items
curl "https://<expert-review-api-id>.execute-api.us-east-1.amazonaws.com/prod/?filter=all"
```

### Running Tests

```bash
# Run inference integration test
./scripts/test_inference.sh
```

---

## Functional Requirements

### FR-1: Defect Detection
- System SHALL accept base64-encoded images
- System SHALL classify images into 6 defect categories
- System SHALL return confidence scores for predictions
- System SHALL support BMP, JPG, and PNG image formats

### FR-2: Report Generation
- System SHALL generate CAPA reports for detected defects
- System SHALL include 5-Why analysis in reports
- System SHALL include Fishbone (6M) analysis in reports
- System SHALL include 8D report structure
- System SHALL use RAG with seed reports for context

### FR-3: Feedback Collection
- System SHALL accept agree/disagree feedback
- System SHALL capture corrected class for disagreements
- System SHALL auto-flag low-confidence predictions
- System SHALL auto-flag user disagreements

### FR-4: Expert Review
- System SHALL maintain queue of flagged items
- System SHALL support filtering by review status
- System SHALL sort by priority (flagged first, then timestamp)

### FR-5: Auto-Trigger Logic
- System SHALL auto-generate reports when confidence > 0.95
- System SHALL auto-flag feedback when confidence < 0.90
- System SHALL auto-flag feedback on user disagreement

---

## Non-Functional Requirements

### NFR-1: Performance
- Inference latency SHALL be < 30 seconds for 90th percentile
- Report generation SHALL complete within 60 seconds
- API response time SHALL be < 5 seconds for feedback/review

### NFR-2: Scalability
- System SHALL handle concurrent inference requests
- System SHALL scale automatically with Lambda concurrency
- DynamoDB SHALL use on-demand capacity for auto-scaling

### NFR-3: Availability
- System SHALL leverage AWS multi-AZ infrastructure
- DynamoDB SHALL have point-in-time recovery enabled
- S3 SHALL use standard redundancy (99.999999999% durability)

### NFR-4: Security
- API Gateway SHALL enforce HTTPS
- Lambda functions SHALL use least-privilege IAM roles
- S3 buckets SHALL block public access
- DynamoDB SHALL encrypt data at rest

### NFR-5: Maintainability
- Infrastructure SHALL be defined as code (CDK)
- System SHALL use modular stack architecture
- Logs SHALL be captured in CloudWatch

### NFR-6: Cost Efficiency
- Resources SHALL use pay-per-use billing
- S3 lifecycle rules SHALL clean up old data
- Lambda memory SHALL be right-sized per function

---

## Possible Improvements

### Short-Term Improvements

1. **Authentication & Authorization**
   - Add API Gateway authorizers (Cognito/IAM)
   - Implement user roles (operator, expert, admin)
   - Add API keys for rate limiting

2. **Input Validation**
   - Add image size/format validation
   - Implement request schema validation
   - Add rate limiting per user/IP

3. **Error Handling**
   - Implement dead letter queues for failed requests
   - Add retry logic for transient failures
   - Improve error messages and logging

4. **Monitoring & Observability**
   - Add CloudWatch dashboards
   - Implement X-Ray tracing
   - Set up alerting for errors/latency

### Medium-Term Improvements

5. **Model Improvements**
   - Implement model versioning
   - Add A/B testing for model comparisons
   - Create automated retraining pipeline
   - Add ensemble models for higher accuracy

6. **Report Enhancements**
   - Add PDF export functionality
   - Implement report templates
   - Add visualization (charts/graphs)
   - Support multiple languages

7. **Feedback Loop**
   - Implement expert annotation interface
   - Create dataset management system
   - Add active learning for efficient labeling

8. **Search & Analytics**
   - Add full-text search for reports
   - Implement analytics dashboard
   - Create defect trend analysis

### Long-Term Improvements

9. **Real-Time Processing**
   - Add video stream support
   - Implement edge inference (AWS Greengrass)
   - Create real-time alerting system

10. **Integration**
    - Add webhook notifications
    - Integrate with ERP/MES systems
    - Implement batch processing API

11. **Advanced ML Features**
    - Add defect localization (bounding boxes)
    - Implement severity scoring
    - Create anomaly detection for new defect types

12. **Multi-Tenancy**
    - Add organization/tenant support
    - Implement data isolation
    - Create custom model training per tenant

---

## Cost Considerations

### Pay-Per-Use Resources

| Resource | Billing Model |
|----------|---------------|
| Lambda | Duration × Memory |
| API Gateway | Requests + Data Transfer |
| DynamoDB | On-demand (Read/Write Units) |
| S3 | Storage + Requests |
| Bedrock | Claude token usage |

### Cost Optimization Strategies

- **S3 Lifecycle Rules:** Images auto-delete after 90 days, reports after 365 days
- **Lambda Memory:** Right-sized per function (256MB - 3008MB)
- **DynamoDB:** On-demand mode (no minimum cost)
- **Model Caching:** Model cached in Lambda memory between invocations

### Estimated Costs (US East)

| Component | Low Usage | Medium Usage | High Usage |
|-----------|-----------|--------------|------------|
| Lambda | ~$5/month | ~$50/month | ~$500/month |
| API Gateway | ~$3/month | ~$30/month | ~$300/month |
| DynamoDB | ~$1/month | ~$10/month | ~$100/month |
| S3 | ~$1/month | ~$5/month | ~$50/month |
| Bedrock | ~$10/month | ~$100/month | ~$1000/month |

*Costs vary based on usage patterns and AWS region.*

---

## License

[Add appropriate license]

---

## Contributing

[Add contribution guidelines]

---

## Support

For issues and questions, please open an issue in the repository.
