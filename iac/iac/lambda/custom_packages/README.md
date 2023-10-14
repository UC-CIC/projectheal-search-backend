# we are pinning to urllib3 less than 2 to fix an error with boto3 compatability seen below:
# Runtime.ImportModuleError: Unable to import module 'index': cannot import name 'DEFAULT_CIPHERS' from 'urllib3.util.ssl_' 
```
mkdir -p src
cd src
mkdir python
cd python
pip install requests "urllib3<2" -t .
pip install --upgrade opensearch-py "urllib3<2" -t .
pip install --upgrade requests-aws4auth "urllib3<2" -t .
rm -rf *dist-info
```

zip up the python dir and drop in layers.