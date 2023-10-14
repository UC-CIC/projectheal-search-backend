#!/usr/bin/env python3
import json

import aws_cdk as cdk

from aws_cdk import (
  Stack,
  aws_iam as iam
)
from constructs import Construct


class AOSSIamStack(Stack):

  def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
    super().__init__(scope, construct_id, **kwargs)

    #################################################################################
    # Custom lambda execution role for AOSS
    #################################################################################
    aoss_role = iam.Role(self, "aoss-role",
      assumed_by=iam.CompositePrincipal(
        iam.ServicePrincipal("lambda.amazonaws.com")
        )
    )

    self.aoss_role = aoss_role