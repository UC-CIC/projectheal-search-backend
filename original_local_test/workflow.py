import boto3
import os
import json
import requests
import ast
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth

opensearch_host = 'hx4qn022z9dt6poc7u9l.us-west-2.aoss.amazonaws.com'
opensearch_region = 'us-west-2' 
opensearch_service = 'aoss'
opensearch_index_name = "misinfo-index-cosine"


def create_query_list(meta):
  query_string_list = []
  for key,values in meta.items():
   for eachvalue in values:
      query = {
                "query_string": {
                  "query": eachvalue,
                  "fields": [
                    "metadata." + key
                  ]
                }
              }
      query_string_list.append(query)
  return query_string_list


def generateMetadataComprehend(input_statement):
  meta = {}
  client = boto3.client(service_name='comprehendmedical', region_name='us-west-2')
  result = client.detect_entities_v2(Text= input_statement)
  out_file = open("comprehendresults.json", "w") 
  json.dump(result['Entities'], out_file, indent=4) 
  print(result['Entities'])

  for entity in result['Entities']:
      if entity["Score"] > 0.75:
          entity["Category"] = entity["Category"].lower()
          metanew = ''.join(e for e in entity["Category"] if e.isalnum())
          if metanew not in meta.keys():
            meta[metanew] = []
          meta[metanew].append(entity["Text"])

  return meta


def generateEmbeddings(input_statement):
  headers = {
      'x-api-key': os.environ["embedding_apikey"],
      'Content-Type': 'application/json',
  }
  json_data = {
      'inputText': input_statement,
  }

  response = requests.post(
      'https://686c6u63fb.execute-api.us-east-1.amazonaws.com/prod/api/generate/embeddings',
      headers=headers,
      json=json_data,
  )
  print(response.text)
  print(response.status_code)
  if response.status_code == 200:
      vector_embedding = response.text
  return vector_embedding

def searchDocument(vector_embedding, query_string_list):
    credentials = boto3.Session().get_credentials()
    auth = AWSV4SignerAuth(credentials, opensearch_region, opensearch_service)

    # create an opensearch client and use the request-signer
    client = OpenSearch(
        hosts=[{'host': opensearch_host, 'port': 443}],
        http_auth=auth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        pool_maxsize=20,
    )

    query = {
      'size': 5,
      'query': {
        'knn': {
          "misinfo-vector": {
              "vector": ast.literal_eval(vector_embedding),
              "k": 5
          }
        }
      },
      "post_filter": {
        "bool": {
          "should": query_string_list
        }
      },
      "fields": ["statement"]
    }

    response = client.search(
        body = query,
        index = opensearch_index_name
    )
    return(response)
   

def ingestDocument(input_statement):
    # create an opensearch client and use the request-signer
    credentials = boto3.Session().get_credentials()
    auth = AWSV4SignerAuth(credentials, opensearch_region, opensearch_service)

    client = OpenSearch(
        hosts=[{'host': opensearch_host, 'port': 443}],
        http_auth=auth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        pool_maxsize=20,
    )
    response = client.index(
        index = opensearch_index_name,
        body = document
    )
    return response

def mapDocumentInDynamoDB(client, hits):
   response = client.put_item(
              Item={
                  'Statement': {
                      'S': input_statement,
                  },
                  'Similarity Score': {
                      'N': str(hits["_score"]),
                  },
                  'SimilarStatement': {
                      'S': hits["_source"]['statement'],
                  },
              },
              TableName='DocumentSimilarityMap'
          )
   return response
   
# Generate metadata using Comprehend Medical
input_statement = input("Enter statement: ")
meta = generateMetadataComprehend(input_statement)
print(meta)

# create metadata for Opensearch query 
query_string_list = create_query_list(meta)
print(query_string_list)

# Create vector embedding
vector_embedding = generateEmbeddings(input_statement)

# search query Opensearch
search_response = searchDocument(vector_embedding, query_string_list)

# Ingest or map in DynamoDB
if (search_response['hits']['hits'] == []):
    print("Document not found. Ingesting...")
    document = {
      'misinfo-vector': ast.literal_eval(vector_embedding),
      'statement': input_statement,
      'metadata' : meta
    }

    resp = ingestDocument(document)
    print(resp)

else:
    client = boto3.client('dynamodb')
    for hits in search_response['hits']['hits']:
        print(hits["_score"])
        print(hits["_source"]['statement'])
        if ((hits["_score"] > 0.7) and (hits["_score"] < 1)):
            response = mapDocumentInDynamoDB(client, hits)
            print(response)
            
