#!/bin/bash

echo ~~Be sure to SET embeddings_api_key=value~~
echo ~~Be sure to SET embeddings_api=value~~
echo ~~Start Processing~~

layer_arn="$(python3 layers_get_latest.py layer_aoss)"
for var in "$@"
do
    cdk destroy $var --context layer_arn=$layer_arn --context embeddings_api=$embeddings_api --context embeddings_api_key=$embeddings_api_key
done