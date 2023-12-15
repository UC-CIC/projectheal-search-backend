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
comprehend_client = boto3.client('comprehendmedical')

region = boto3.Session().region_name
service = 'aoss'
credentials = boto3.Session().get_credentials()
awsauth = AWS4Auth(credentials.access_key, credentials.secret_key, region, service, session_token=credentials.token)
host=AOSS_ENDPOINT.replace("https://", "")
aoss_index_name='statements'
headers = { "Content-Type": "application/json" }



def generate_statement_metadata(statement):
    THRESHOLD = .75
    meta = {}
    topics = set()
    result = comprehend_client.detect_entities_v2(Text=statement)
    print("Comprehend Medical Result")
    print( result )
    
    for entity in result['Entities']:
        if entity["Score"] > THRESHOLD:
            # topics.append(entity["Category"].replace('_', ' ').lower())
            topics.add(entity["Category"].replace('_', ' ').lower())
            entity["Category"] = entity["Category"].lower()
            metanew = ''.join(e for e in entity["Category"] if e.isalnum())
            if metanew not in meta.keys():
                meta[metanew] = []
            meta[metanew].append(entity["Text"].lower())


    return meta, list(topics)

def generate_statement_background(statement, intent, severity, source, topics):
    back = {
        "intent": intent,
        "severity": severity,
        "source": source,
        "topic": topics
    } 

    return back


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
    print(response)

    vector_embedding = None
    if response.status_code == 200:
        vector_embedding = response.json()
    else:
        print(response.text)

    return vector_embedding


def create_filters(metadata):
    filter_list = []
    for key,values in metadata.items():
        for filter_item in values:
            query = {
                "query_string": {
                    "query": filter_item,
                    "fields": [
                        "metadata." + key
                    ]
                }
            }
            filter_list.append(query)
    return filter_list

def search_aoss(embeddings,filter_list):
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
        'size': 20,
        'query': {
            'knn': {
                "statement-vector": {
                    "vector": embeddings,
                    "k": 5
                }
            }
        },
        "post_filter": {
            "bool": {
                "should": filter_list
            }
        },
        "fields": ["statement"]
    }    

    response = client.search(
        body = query,
        index = aoss_index_name
    )
    return(response)


def ingest_document(document,doc_id=None):
    # Build the OpenSearch client
    client = OpenSearch(
        hosts=[{'host': host, 'port': 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=300
    )
    response = None
    if( doc_id is None ):
        response = client.index(
            index = aoss_index_name,
            body = document
        )
    else:
         print("~~~~~~~~UPDATE~~~~~~~")
         
         response = client.update(
            index = aoss_index_name,
            body = document,
            id=doc_id
        )
                
    return response


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

def strip_punctuation(sentence):
    # Create a translation table to remove punctuation
    translator = str.maketrans('', '', string.punctuation)

    # Use translate to remove punctuation from the sentence
    stripped_sentence = sentence.translate(translator)

    return stripped_sentence


def map_statement(statement_document,statement_metadata,statement_backdata,matches):
    THRESHOLD = 0.8
    mapped_counter = 0
    # Build the OpenSearch client
    client = OpenSearch(
        hosts=[{'host': host, 'port': 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=300
    )
    # remember breaker for match on 1
    for result in matches:
        if (THRESHOLD <= result['_score'] < 1 ):
            print("Result match, updating similar statement payload")
            doc_id=result["_id"]

            statement=statement_document["statement"]
            doc_data=result["_source"]

            statement_similar_json=doc_data["statement-similar"]
            statement_similar_json[ statement ] = {"metadata":statement_metadata, "background": statement_backdata}
            print("~~~SIMILAR-STATEMENT~~~~")
            print(statement_similar_json)
            
            update_data = {
                "doc": {
                    "statement-similar":statement_similar_json
                }
            }

            mapped_counter += 1
            
            response = ingest_document(update_data,doc_id=doc_id)

            print(response)
        elif( result['_score'] == 1 ):
            # doc_id=result["_id"]
            mapped_counter+=1
            print("EXACT MATCH, BYPASS ACTION")
            # update_data = {
            #     "doc": {
            #         "background":statement_backdata
            #     }
            # }
            # response = ingest_document(update_data,doc_id=doc_id)

            # print(response)
    
    # no matches met threshold, create a new one
    if( mapped_counter == 0 ):
        print("No threshold matches, creating a new document")
        response = ingest_document(statement_document)






def handler(event,context):
    print("<Ingest:Hello>")
    field_values=json.loads(event["body"])
    # field_values = event
    # print(field_values)
    print(event["body"])
    
    try:
        statement=strip_punctuation(field_values["statement"].lower())
        intent=field_values["intent"].lower()
        severity=field_values["severity"].lower()
        source=field_values["source"].lower()
        # statement=strip_punctuation(event["statement"].lower())
        # print(event["statement"])
        # print(statement)

        index_exists = index_check()
        print(type(index_exists))

        if( index_exists==False ):
            print("Index does not exist")
            index_create()

            wait_checks=0
            wait_breaker=5
            # Poll and wait for the index to be created
            while not index_check():
                print(f"Index  is not yet created. Waiting...")
                time.sleep(5)  # Sleep for 5 seconds before checking again
                wait_checks+=1
                if wait_checks >= wait_breaker:
                    raise ValueError("AOSS Index Creation error. Waited to long. Breaking loop.")
        
        metadata, topics=generate_statement_metadata(statement)
        print(metadata)
        backdata=generate_statement_background(statement, intent, severity, source, topics)
        print(backdata)
        embeddings=generate_embeddings(statement)
        # print(embeddings)
        filter_list = create_filters(metadata)
        print(filter_list)

        search_results = search_aoss(embeddings=embeddings,filter_list=filter_list)

        document = {
            'statement': statement,
            'statement-vector': embeddings,
            'statement-similar': {},
            'metadata': metadata,
            'background': backdata
        }

        # Ingest or map to results
        if (search_results['hits']['max_score'] == None):
            print("No results found; ingesting...")
            response=ingest_document(document)
            print(response)
        else:
            print(strip_knn_vector(search_results))
            print("Results found; mapping...")
            response=map_statement(statement_document=document,statement_metadata=metadata,statement_backdata=backdata,matches=search_results['hits']['hits'])
            
        
        print("Explicit wait so indices can refresh ;)....  15 seconds")
        time.sleep(15)  # Sleep for 15 seconds to "ensure" that results are refreshed on index and available for next API call
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
