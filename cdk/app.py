#!/usr/bin/env python3
import sys
from pathlib import Path
from stacks.report_generator_stack import ReportGeneratorStack
from stacks.feedback_stack import FeedbackStack
from stacks.expert_review_stack import ExpertReviewStack
from stacks.expert_approve_stack import ExpertApproveStack
from stacks.reports_crud_stack import ReportsCrudStack
from stacks.images_stack import ImagesStack
from stacks.create_class_stack import CreateClassStack
from stacks.training_stats_stack import TrainingStatsStack
from stacks.retraining_stack import RetrainingStack
from stacks.auth_stack import AuthStack
from stacks.model_management_stack import ModelManagementStack
from stacks.checkpoint_stack import CheckpointStack
# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import aws_cdk as cdk
from stacks.storage_stack import StorageStack  # ← Changed from CapaStorageStack
from stacks.inference_stack import CapaInferenceStack

app = cdk.App()

# Deploy auth stack (Cognito)
auth_stack = AuthStack(app, "CapaAuthStack")

# Deploy storage stack
storage_stack = StorageStack(app, "CapaStorageStack")  # ← Keep the stack ID same

# Deploy inference stack
inference_stack = CapaInferenceStack(
    app, "CapaInferenceStack",
    storage_stack=storage_stack,
    auth_stack=auth_stack
)
inference_stack.add_dependency(storage_stack)
inference_stack.add_dependency(auth_stack)

# Deploy report generator stack
report_stack = ReportGeneratorStack(
    app, "CapaReportGeneratorStack",
    storage_stack=storage_stack,
    auth_stack=auth_stack
)
report_stack.add_dependency(storage_stack)
report_stack.add_dependency(auth_stack)

# Deploy feedback stack
feedback_stack = FeedbackStack(
    app, "CapaFeedbackStack",
    storage_stack=storage_stack,
    auth_stack=auth_stack
)
feedback_stack.add_dependency(storage_stack)
feedback_stack.add_dependency(auth_stack)

# Deploy expert review stack (Expert only)
expert_review_stack = ExpertReviewStack(
    app, "CapaExpertReviewStack",
    storage_stack=storage_stack,
    auth_stack=auth_stack
)
expert_review_stack.add_dependency(storage_stack)
expert_review_stack.add_dependency(auth_stack)

# Deploy expert approve stack (Expert only)
expert_approve_stack = ExpertApproveStack(
    app, "CapaExpertApproveStack",
    storage_stack=storage_stack,
    auth_stack=auth_stack
)
expert_approve_stack.add_dependency(storage_stack)
expert_approve_stack.add_dependency(auth_stack)

# Deploy reports CRUD stack
reports_crud_stack = ReportsCrudStack(
    app, "CapaReportsCrudStack",
    storage_stack=storage_stack,
    auth_stack=auth_stack
)
reports_crud_stack.add_dependency(storage_stack)
reports_crud_stack.add_dependency(auth_stack)

# Deploy images stack
images_stack = ImagesStack(
    app, "CapaImagesStack",
    storage_stack=storage_stack,
    auth_stack=auth_stack
)
images_stack.add_dependency(storage_stack)
images_stack.add_dependency(auth_stack)

# Deploy create class stack (Expert only)
create_class_stack = CreateClassStack(
    app, "CapaCreateClassStack",
    storage_stack=storage_stack,
    auth_stack=auth_stack
)
create_class_stack.add_dependency(storage_stack)
create_class_stack.add_dependency(auth_stack)

# Deploy training stats stack (Expert only)
training_stats_stack = TrainingStatsStack(
    app, "CapaTrainingStatsStack",
    storage_stack=storage_stack,
    auth_stack=auth_stack
)
training_stats_stack.add_dependency(storage_stack)
training_stats_stack.add_dependency(auth_stack)

# Deploy retraining stack (Expert only)
retraining_stack = RetrainingStack(
    app, "CapaRetrainingStack",
    storage_stack=storage_stack,
    auth_stack=auth_stack
)
retraining_stack.add_dependency(storage_stack)
retraining_stack.add_dependency(auth_stack)

# Deploy model management stack (Expert only)
model_management_stack = ModelManagementStack(
    app, "CapaModelManagementStack",
    model_bucket=storage_stack.model_bucket,
)
model_management_stack.add_dependency(storage_stack)

# Deploy checkpoint management stack (Expert only)
checkpoint_stack = CheckpointStack(
    app, "CapaCheckpointStack",
    storage_stack=storage_stack,
    auth_stack=auth_stack
)
checkpoint_stack.add_dependency(storage_stack)
checkpoint_stack.add_dependency(auth_stack)

app.synth()
