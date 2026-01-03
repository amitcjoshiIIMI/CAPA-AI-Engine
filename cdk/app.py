#!/usr/bin/env python3
import sys
from pathlib import Path
from stacks.report_generator_stack import ReportGeneratorStack

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

app.synth()
