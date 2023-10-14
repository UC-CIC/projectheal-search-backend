```
mkdir -p src
cd src
mkdir python
cd python
pip install requests -t .
pip install --upgrade opensearch-py -t .
pip install --upgrade requests-aws4auth -t .
rm -rf *dist-info
```

zip up the python dir and drop in layers.