import boto3
import json
import requests
from requests_aws4auth import AWS4Auth
from opensearchpy import OpenSearch, RequestsHttpConnection
import os



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
comprehend_client = boto3.client('comprehendmedical')

region = boto3.Session().region_name
service = 'aoss'
credentials = boto3.Session().get_credentials()
awsauth = AWS4Auth(credentials.access_key, credentials.secret_key, region, service, session_token=credentials.token)
host=AOSS_ENDPOINT.replace("https://", "")
aoss_index_name='statements'
headers = { "Content-Type": "application/json" }



def generate_statement_metadata(statement):
    meta = {}
    result = comprehend_client.detect_entities_v2(Text=statement)
    print("Comprehend Medical Result")
    print( result )
    
    for entity in result['Entities']:
        if entity["Score"] > 0.75:
            entity["Category"] = entity["Category"].lower()
            metanew = ''.join(e for e in entity["Category"] if e.isalnum())
            if metanew not in meta.keys():
                meta[metanew] = []
            meta[metanew].append(entity["Text"])


    return meta


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

def index_create():
    # Build the OpenSearch client
    client = OpenSearch(
        hosts=[{'host': host, 'port': 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=300
    )

    response = client.indices.create(
        aoss_index_name,
        body={
            "settings": {
                "index.knn": True
            },
            "mappings": {
                "properties": {
                    "statement-vector": {
                        "type": "knn_vector",
                        "dimension": 1536,
                        "method": {
                            "name": "hnsw",
                            "space_type": "cosinesimil",
                            "engine": "nmslib",
                            "parameters": {
                                "ef_construction": 512,
                                "m": 32
                            }
                        }
                    },
                    "statement": {
                        "type": "text"
                    },
                    "statement-similar": {
                        "type": "object"
                    }
                }
            }
        })
    
    print('\nCreating index:')
    print(response)

def generate_embeddings(statement):
    headers = {
        'x-api-key': EMBEDDINGS_API_KEY,
        'Content-Type': 'application/json',
    }
    json_data = {
        'inputText': statement,
    }

    response = requests.post(
        EMBEDDINGS_API,
        headers=headers,
        json=json_data,
    )

    if response.status_code == 200:
        vector_embedding = response.text

    return vector_embedding

def handler(event,context):
    print("<Ingest:Hello>")
    field_values=json.loads(event["body"])
    
    try:
        statement=field_values["statement"]

        index_exists = index_check()
        print(type(index_exists))

        if( index_exists==False ):
            print("Index does not exist")
            index_create()
        
        metadata=generate_statement_metadata(statement)
        embeddings=generate_embeddings(statement)
        print(embeddings)

        return {
            "statusCode":200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"Hello world":AOSS_ENDPOINT})
        }
    except Exception as e:
        return {
            "statusCode":500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"msg":str(e)})
        }