import json
import os
import re
from collections import Counter

import boto3

s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
DEFAULT_BUCKET = os.environ.get("DATA_BUCKET")

STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "and", "or", "but", "if", "of", "to", "in", "on", "for", "with",
    "this", "that", "these", "those", "it", "its", "as", "by", "at",
    "from", "into", "about", "also", "which", "what", "how", "where",
}


def tokenize(text):
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 1]


def build_index(chunks_doc, file_name):
    out_chunks = []
    for chunk in chunks_doc["chunks"]:
        tf = dict(Counter(tokenize(chunk["text"])))
        out_chunks.append({
            "chunkId": chunk["chunkId"],
            "text": chunk["text"],
            "startSec": chunk.get("startSec"),
            "endSec": chunk.get("endSec"),
            "pageStart": chunk.get("pageStart"),
            "pageEnd": chunk.get("pageEnd"),
            "tf": tf,
        })

    return {
        "documentId": chunks_doc["documentId"],
        "fileName": file_name,
        "sourceType": chunks_doc["sourceType"],
        "method": "tfidf-v1",
        "chunks": out_chunks,
    }


def lambda_handler(event, context):
    user_id = event["userId"]
    document_id = event["documentId"]
    bucket = event.get("bucket", DEFAULT_BUCKET)
    chunks_key = event.get("chunksKey", f"processed/{user_id}/{document_id}/chunks.json")
    file_name = event.get("fileName", "")

    obj = s3.get_object(Bucket=bucket, Key=chunks_key)
    chunks_doc = json.loads(obj["Body"].read())

    result = build_index(chunks_doc, file_name)

    out_key = f"processed/{user_id}/{document_id}/index.json"
    s3.put_object(
        Bucket=bucket,
        Key=out_key,
        Body=json.dumps(result).encode(),
        ContentType="application/json",
    )

    return {"indexKey": out_key, "chunkCount": len(chunks_doc["chunks"])}
