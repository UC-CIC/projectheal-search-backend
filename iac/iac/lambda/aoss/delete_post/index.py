import boto3
import json
import requests
from requests_aws4auth import AWS4Auth
from opensearchpy import OpenSearch, RequestsHttpConnection
import os
import time
import string

CORS_HEADERS = {
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Origin': os.environ["CORS_ALLOW_UI"] if os.environ["LOCALHOST_ORIGIN"] == "" else os.environ["LOCALHOST_ORIGIN"],
    'Access-Control-Allow-Methods': 'OPTIONS,POST,GET'
}
AOSS_ENDPOINT = os.environ["AOSS_ENDPOINT"]
EMBEDDINGS_API = os.environ["EMBEDDINGS_API"]
EMBEDDINGS_API_KEY = os.environ["EMBEDDINGS_API_KEY"]

#################################
# References
# https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-sdk.html
# https://docs.aws.amazon.com/opensearch-service/latest/developerguide/search-example.html
# https://opensearch-project.github.io/opensearch-py/api-ref/clients/indices_client.html
#################################

aoss_client = boto3.client('opensearchserverless')

region = boto3.Session().region_name
service = 'aoss'
credentials = boto3.Session().get_credentials()
awsauth = AWS4Auth(credentials.access_key, credentials.secret_key, region, service, session_token=credentials.token)
host=AOSS_ENDPOINT.replace("https://", "")
aoss_index_name='statements'
headers = { "Content-Type": "application/json" }

def index_check():
    # Build the OpenSearch client
    client = OpenSearch(
        hosts=[{'host': host, 'port': 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=300
    )

    response = client.indices.exists(aoss_index_name)
    print('\Checking index:')
    print(response)
    return response


def delete_document(doc_id=None):
    # Build the OpenSearch client
    client = OpenSearch(
        hosts=[{'host': host, 'port': 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=300
    )

    response = client.delete(
            index = aoss_index_name,
            id = doc_id
        )
    
    return response


def handler(event,context):
    print("<Ingest:Hello>")
    field_values=json.loads(event["body"])

    print(event["body"])
    
    try:
        # id of document to delete
        doc=field_values["id"]

        index_exists = index_check()
        print(type(index_exists))

        if( index_exists==False ):
            print("Index does not exist")
            return []

        response=delete_document(doc)
        print(response)
        return {
            "statusCode":200,
            "headers": CORS_HEADERS,
            "body": "Successfully deleted"
        }
    except Exception as e:
        return {
            "statusCode":500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"msg":str(e)})
        }
