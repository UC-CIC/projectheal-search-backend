import boto3
import sys

latest_version_arn=""
layer_name=sys.argv[1]
try:
    client=boto3.client("lambda")
    response = client.list_layer_versions(LayerName=layer_name,MaxItems=1)
    latest_version_arn = response["LayerVersions"][0]["LayerVersionArn"]
    print(latest_version_arn)
except Exception as e:
    print(e)
    print("")