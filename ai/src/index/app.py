import json
import os
import re
from collections import defaultdict

import boto3

s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
BUCKET = os.environ.get("DATA_BUCKET")

STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "and", "or", "but", "if", "of", "to", "in", "on", "for", "with",
    "this", "that", "these", "those", "it", "its", "as", "by", "at",
    "from", "into", "about", "also", "which", "what", "how", "where",
}


def tokenize(text):
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 1]


def build_index(chunks_doc):
    inverted = defaultdict(set)
    for chunk in chunks_doc["chunks"]:
        for word in tokenize(chunk["text"]):
            inverted[word].add(chunk["chunkId"])

    index = {word: sorted(ids) for word, ids in inverted.items()}
    return {"documentId": chunks_doc["documentId"], "index": index}


def lambda_handler(event, context):
    user_id = event["userId"]
    document_id = event["documentId"]
    chunks_key = event.get("chunksKey", f"processed/{user_id}/{document_id}/chunks.json")

    obj = s3.get_object(Bucket=BUCKET, Key=chunks_key)
    chunks_doc = json.loads(obj["Body"].read())

    result = build_index(chunks_doc)

    out_key = f"processed/{user_id}/{document_id}/index.json"
    s3.put_object(
        Bucket=BUCKET,
        Key=out_key,
        Body=json.dumps(result).encode(),
        ContentType="application/json",
    )

    return {"indexKey": out_key, "chunkCount": len(chunks_doc["chunks"])}
