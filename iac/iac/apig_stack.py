import os

from constructs import Construct
from aws_cdk import(
    Stack,
    aws_apigateway as apigateway,
    aws_lambda as lambda_
)

class ApigStack(Stack):
    def __init__(self,scope: Construct, construct_id: str,  AOSS_ENDPOINT:str, ALO:bool,**kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        LOCALHOST_ORIGIN="http://localhost:3000"
        ALLOW_LOCALHOST_ORIGIN=ALO

        core_api = apigateway.RestApi(
            self,"core-api",
            endpoint_configuration=apigateway.EndpointConfiguration(
                types=[apigateway.EndpointType.REGIONAL]
            ),
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_methods=['GET', 'OPTIONS','PUT','PATCH','POST'],
                allow_origins=[LOCALHOST_ORIGIN if ALLOW_LOCALHOST_ORIGIN else ""])
        )

        ###### Route Base = /api [match for cloud front purposes]
        api_route = core_api.root.add_resource("api")


        #################################################################################
        # /hello
        #################################################################################        
        fn_hello_get = lambda_.Function(
            self,"fn-hello-get",
            description="hello-get", #microservice tag
            runtime=lambda_.Runtime.PYTHON_3_10,
            handler="index.handler",
            code=lambda_.Code.from_asset(os.path.join("iac/lambda/hello","hello_get")),
            environment={
                "AOSS_ENDPOINT": AOSS_ENDPOINT.value,
                "LOCALHOST_ORIGIN":LOCALHOST_ORIGIN if ALLOW_LOCALHOST_ORIGIN else ""
            }
        )

        ###### Route Base = /hello
        pr_hello=api_route.add_resource("hello")
        # GET /hello
        intg_hello_get=apigateway.LambdaIntegration(fn_hello_get)
        method_questionnaire_prohash=pr_hello.add_method(
            "GET",intg_hello_get,
            api_key_required=True
        )

        #################################################################################
        # Usage plan and api key to "lock" API
        #################################################################################
        plan = core_api.add_usage_plan(
            "UsagePlan",name="public plan",
            throttle=apigateway.ThrottleSettings(
                rate_limit=10,
                burst_limit=2
            )
        )

        core_key=core_api.add_api_key("core-api-key")
        plan.add_api_key(core_key)
        plan.add_api_stage(api=core_api,stage=core_api.deployment_stage)

        self.core_api = core_api        