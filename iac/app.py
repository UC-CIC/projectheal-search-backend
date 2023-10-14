#!/usr/bin/env python3
import os

import aws_cdk as cdk

from iac.aoss_vector_stack import AOSSVectorStack
from iac.apig_stack import ApigStack
from iac.layers import LayersStack


ALLOW_LOCALHOST_ORIGIN=True

app = cdk.App()

LayersStack(app, "cdk-layers-stack")
aoss_stack = AOSSVectorStack(app, "cdk-aoss-vector-stack")
apig_stack = ApigStack(app, "cdk-apig-stack", AOSS_ROLE=aoss_stack.aoss_role,AOSS_ENDPOINT=aoss_stack.aoss_endpoint, ALO=ALLOW_LOCALHOST_ORIGIN)


app.synth()
