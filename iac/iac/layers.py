import os

from constructs import Construct
from aws_cdk import(
    Stack,
    aws_lambda as lambda_
)

class LayersStack(Stack):
    def __init__(self,scope: Construct, construct_id: str,  **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        layer_aoss_lib = lambda_.LayerVersion(
            self, "layer_aoss",
            code=lambda_.Code.from_asset(os.path.join("iac/lambda/custom_packages/layers","aoss-layer.zip")),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_10],
            description="Various modules to support AOSS calls",
            layer_version_name="layer_aoss"
        )