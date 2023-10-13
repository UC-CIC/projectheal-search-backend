#!/usr/bin/env python3
import os

import aws_cdk as cdk

from iac.aoss_vector_stack import AOSSVectorStack


app = cdk.App()

aoss_stack = AOSSVectorStack(app, "cdk-aoss-vector-stack")


app.synth()
