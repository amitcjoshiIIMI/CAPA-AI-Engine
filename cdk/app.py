#!/usr/bin/env python3
import sys
from pathlib import Path
from stacks.report_generator_stack import ReportGeneratorStack
from stacks.feedback_stack import FeedbackStack
from stacks.expert_review_stack import ExpertReviewStack
from stacks.expert_approve_stack import ExpertApproveStack
from stacks.reports_crud_stack import ReportsCrudStack
from stacks.images_stack import ImagesStack

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import aws_cdk as cdk
from stacks.storage_stack import StorageStack  # ← Changed from CapaStorageStack
from stacks.inference_stack import CapaInferenceStack

app = cdk.App()

# Deploy storage stack
storage_stack = StorageStack(app, "CapaStorageStack")  # ← Keep the stack ID same

# Deploy inference stack
inference_stack = CapaInferenceStack(
    app, "CapaInferenceStack",
    storage_stack=storage_stack
)

inference_stack.add_dependency(storage_stack)

# Deploy report generator stack
report_stack = ReportGeneratorStack(
    app, "CapaReportGeneratorStack",
    storage_stack=storage_stack
)
report_stack.add_dependency(storage_stack)

# Deploy feedback stack
feedback_stack = FeedbackStack(
    app, "CapaFeedbackStack",
    storage_stack=storage_stack
)
feedback_stack.add_dependency(storage_stack)

# Deploy expert review stack
expert_review_stack = ExpertReviewStack(
    app, "CapaExpertReviewStack",
    storage_stack=storage_stack
)
expert_review_stack.add_dependency(storage_stack)

# Deploy expert approve stack
expert_approve_stack = ExpertApproveStack(
    app, "CapaExpertApproveStack",
    storage_stack=storage_stack
)
expert_approve_stack.add_dependency(storage_stack)

# Deploy reports CRUD stack (NEW - for listing/viewing reports)
reports_crud_stack = ReportsCrudStack(
    app, "CapaReportsCrudStack",
    storage_stack=storage_stack
)
reports_crud_stack.add_dependency(storage_stack)

# Deploy images stack (NEW - for uploading/downloading images)
images_stack = ImagesStack(
    app, "CapaImagesStack",
    storage_stack=storage_stack
)
images_stack.add_dependency(storage_stack)

app.synth()
