import os

from constructs import Construct
from aws_cdk import(
    Duration,
    Stack,
    aws_apigateway as apigateway,
    aws_iam as iam,
    aws_lambda as lambda_
)

class ApigStack(Stack):
    def __init__(self,scope: Construct, construct_id: str,  AOSS_ROLE:iam.Role, AOSS_ENDPOINT:str, ALO:bool,**kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        LOCALHOST_ORIGIN="http://localhost:3000"
        ALLOW_LOCALHOST_ORIGIN=ALO

        layer_aoss = lambda_.LayerVersion.from_layer_version_arn(self,id="layer_aoss",layer_version_arn=self.node.try_get_context("layer_arn"))
        
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
            role=AOSS_ROLE,
            code=lambda_.Code.from_asset(os.path.join("iac/lambda/hello","hello_get")),
            environment={
                "AOSS_ENDPOINT": AOSS_ENDPOINT.value,
                "LOCALHOST_ORIGIN":LOCALHOST_ORIGIN if ALLOW_LOCALHOST_ORIGIN else ""
            },
            layers=[ layer_aoss ]
        )

        ###### Route Base = /hello
        pr_hello=api_route.add_resource("hello")
        # GET /hello
        intg_hello_get=apigateway.LambdaIntegration(fn_hello_get)
        method_hello=pr_hello.add_method(
            "GET",intg_hello_get,
            api_key_required=True
        )


        #################################################################################
        # /aoss
        #################################################################################
        
        # !! IMPORTANT !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
        #
        # This function needs to be updated before any production like environment run.
        # API_KEY should not be stored in Lambda environment variables and instead should
        # be utilizing AWS Secrets Manager/Paramater Store and called within the lambda.
        #
        # Why? It's best security practices. Your key is in plaintext and leaked both in your CF
        # template that is synthesized as well as your environment variable section ;).
        #
        # This is a shortcut being utilized purely for prototyping
        #
        fn_aoss_ingest_post = lambda_.Function(
            self,"fn-aoss-ingest-post",
            description="aoss-ingest-post", #microservice tag
            runtime=lambda_.Runtime.PYTHON_3_10,
            handler="index.handler",
            role=AOSS_ROLE,
            code=lambda_.Code.from_asset(os.path.join("iac/lambda/aoss","ingest_post")),
            environment={
                "AOSS_ENDPOINT": AOSS_ENDPOINT.value,
                "EMBEDDINGS_API": self.node.try_get_context('embeddings_api'),
                "EMBEDDINGS_API_KEY": self.node.try_get_context('embeddings_api_key'),
                "LOCALHOST_ORIGIN":LOCALHOST_ORIGIN if ALLOW_LOCALHOST_ORIGIN else ""
            },
            timeout=Duration.minutes(3),
            layers=[ layer_aoss ]
        )
        #
        # !! IMPORTANT !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
        

        ###### Route Base = /aoss
        pr_aoss=api_route.add_resource("aoss")
        pr_aoss_ingest=pr_aoss.add_resource("ingest")
        # POST /ingest
        intg_ingest_post=apigateway.LambdaIntegration(fn_aoss_ingest_post)
        method_ingest=pr_aoss_ingest.add_method(
            "POST",intg_ingest_post,
            api_key_required=True
        )

        #################################################################################
        # /aoss/search_post
        #################################################################################
        
        #
        fn_aoss_search_post = lambda_.Function(
            self,"fn_aoss_search_post",
            description="aoss-search-post", #microservice tag
            runtime=lambda_.Runtime.PYTHON_3_10,
            handler="index.handler",
            role=AOSS_ROLE,
            code=lambda_.Code.from_asset(os.path.join("iac/lambda/aoss","search_post")),
            environment={
                "AOSS_ENDPOINT": AOSS_ENDPOINT.value,
                "EMBEDDINGS_API": self.node.try_get_context('embeddings_api'),
                "EMBEDDINGS_API_KEY": self.node.try_get_context('embeddings_api_key'),
                "LOCALHOST_ORIGIN":LOCALHOST_ORIGIN if ALLOW_LOCALHOST_ORIGIN else ""
            },
            timeout=Duration.minutes(3),
            layers=[ layer_aoss ]
        )
        #        
        ###### Route Base = /aoss
        pr_aoss_search=pr_aoss.add_resource("search")
        # POST /search
        intg_search_post=apigateway.LambdaIntegration(fn_aoss_search_post)
        method_ingest=pr_aoss_search.add_method(
            "POST",intg_search_post,
            api_key_required=True
        )


        #################################################################################
        # Custom lambda execution role permissions
        #################################################################################
        AOSS_ROLE.attach_inline_policy(iam.Policy(self, "lambda-basic-execution-logging",
            statements=[iam.PolicyStatement(
                actions=["logs:CreateLogGroup","logs:CreateLogStream","logs:PutLogEvents"],
                resources=["*"]
            )             
            ]
        ))
        AOSS_ROLE.attach_inline_policy(iam.Policy(self, "lambda-basic-explicit-invoke",
            statements=[iam.PolicyStatement(
                actions=["lambda:InvokeFunction"],
                resources=[fn_hello_get.function_arn]
            )             
            ]
        ))
        AOSS_ROLE.attach_inline_policy(iam.Policy(self, "lambda-basic-aoss",
            statements=[iam.PolicyStatement(
                actions=["aoss:BatchGetCollection","aoss:APIAccessAll","aoss:DashboardsAccessAll"],
                resources=["*"]
            )             
            ]
        ))
        AOSS_ROLE.attach_inline_policy(iam.Policy(self, "lambda-comprehend-medical",
            statements=[iam.PolicyStatement(
                actions=["comprehendmedical:*"],
                resources=["*"]
            )             
            ]
        ))

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