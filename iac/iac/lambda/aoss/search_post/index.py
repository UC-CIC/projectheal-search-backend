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

    return vector_embedding


def create_filters(metadata, intent, severity, source, topic, medicalconditions):
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

    postfilterlist =[]

    intent_filter = {"term": {"background.intent": intent}} if intent != "" else None
    severity_filter = {"term": {"background.severity": severity}} if severity != "" else None
    source_filter = {"term": {"background.source": source}} if source != "" else None
    topic_filter = {"terms": {"background.topic": topic}} if topic is not None and any(topic) else None   
    medicalconditions_filter = {"terms": {"metadata.medicalcondition": medicalconditions}} if medicalconditions is not None and any(medicalconditions) else None

    if intent_filter:
        postfilterlist.append(intent_filter)
    if severity_filter:
        postfilterlist.append(severity_filter)
    if source_filter:
        postfilterlist.append(source_filter)
    if topic_filter:
        postfilterlist.append(topic_filter)
    if medicalconditions_filter:
        postfilterlist.append(medicalconditions_filter)
    
    postfilter = {
        "bool": {
                "must": postfilterlist
            }
        }

    filter_list.append(postfilter)
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

    print(query)
    
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

def strip_punctuation(sentence):
    # Create a translation table to remove punctuation
    translator = str.maketrans('', '', string.punctuation)

    # Use translate to remove punctuation from the sentence
    stripped_sentence = sentence.translate(translator)

    return stripped_sentence


def map_statement(statement_document,statement_metadata,statement_background,matches):
    THRESHOLD = 0.6

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
    similar_statements = []
    exact_match = []
    for result in matches:
        statement_json={}
        exact_json ={}
        if (THRESHOLD <= result['_score'] < 1 ):
            # print("Result match, updating similar statement payload")
            doc_id=result["_id"]

            statement=statement_document["statement"]
            doc_data=result["_source"]
            print(doc_data)

            exact_json[ doc_data["statement"] ] = {"metadata":doc_data["metadata"], "background": doc_data["background"]}
            exact_match.append(exact_json)
            
            statement_similar_json=doc_data["statement-similar"]
            # statement_similar_json[ statement ] = {"metadata":statement_metadata, "background": statement_background}

            similar_statements.append(statement_similar_json)
        elif( result['_score'] == 1 ):
            print("EXACT MATCH")
            doc_data=result["_source"]
            print(doc_data)

            statement=statement_document["statement"]
            statement_json[ statement ] = {"metadata":doc_data["metadata"], "background": doc_data["background"]}
            exact_match.append(statement_json)

            statement_similar_json=doc_data["statement-similar"]
            similar_statements.append(statement_similar_json)


    return (exact_match, similar_statements)


def handler(event,context):
    print("<Ingest:Hello>")
    field_values=json.loads(event["body"])

    # print(event["body"])
    
    try:
        statement=strip_punctuation(field_values["statement"].lower())
        intent=field_values["intent"].lower()
        severity=field_values["severity"].lower()
        source=field_values["source"].lower()
        # topic=field_values["topics"].lower()
        # medicalconditions=field_values["medicalConditions"].lower()
        topic = [topic.lower() for topic in field_values["topics"]]
        medicalconditions = [condition.lower() for condition in field_values["medicalConditions"]]
        index_exists = index_check()
        print(type(index_exists))

        if( index_exists==False ):
            print("Index does not exist")
            return []
            
        metadata, topics=generate_statement_metadata(statement)
        print(metadata)
        backdata=generate_statement_background(statement, intent, severity, source, topics)
        print(backdata)
        embeddings=generate_embeddings(statement)
        # print(embeddings)
        filter_list = create_filters(metadata, intent, severity, source, topic, medicalconditions)
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
        if (search_results['hits']['max_score'] != None):
            print(strip_knn_vector(search_results))
            print("Results found; mapping...")
            response=map_statement(statement_document=document,statement_metadata=metadata,statement_background=backdata,matches=search_results['hits']['hits'])
            print(response)
        else:
            print("No results found.")
            response=""

        return {
            "statusCode":200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"Search response":response})
        }
    except Exception as e:
        return {
            "statusCode":500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"msg":str(e)})
        }
