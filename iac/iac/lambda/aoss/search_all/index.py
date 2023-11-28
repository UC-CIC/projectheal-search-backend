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

def search_aoss():
    # Build the OpenSearch client
    client = OpenSearch(
        hosts=[{'host': host, 'port': 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=300
    )

    query = {
        "query": {
            "match_all": {}
        }
    }  

    response = client.search(
        body = query,
        index = aoss_index_name
    )
    return(response)

def strip_knn_vector(data):
    try:
        rebuild = []
        for entry in data['hits']['hits']:
            entry["_source"]["statement-vector"]=[-1]
            rebuild.append(entry)
        data['hits']['hits'] = rebuild
        return data
    except:
        return data

def handler(event,context):
    print("<Ingest:Hello>")

    # print(event["body"])
    
    try:
        search_results = search_aoss()
        final = strip_knn_vector(search_results)
        print(final)
        return {
            "statusCode":200,
            "headers": CORS_HEADERS,
            # "body": json.dumps({"All results":final['hits']['hits']})
            "body": json.dumps({"All results":final})

        }



    except Exception as e:
        return {
            "statusCode":500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"msg":str(e)})
        }
