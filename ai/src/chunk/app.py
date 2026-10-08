import json
import os

import boto3

s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
DEFAULT_BUCKET = os.environ.get("DATA_BUCKET")


def make_chunks(doc, document_id, max_chars=500):
    segments = doc["segments"]
    source_type = doc["sourceType"]
    chunks = []
    cur_texts = []
    cur_len = 0
    cur_start = None
    cur_end = None

    def flush():
        nonlocal cur_texts, cur_len, cur_start, cur_end
        if not cur_texts:
            return
        chunk = {
            "text": " ".join(cur_texts),
            "startSec": None,
            "endSec": None,
            "pageStart": None,
            "pageEnd": None,
        }
        if source_type == "audio":
            chunk["startSec"] = cur_start
            chunk["endSec"] = cur_end
        else:
            chunk["pageStart"] = cur_start
            chunk["pageEnd"] = cur_end
        chunks.append(chunk)
        cur_texts = []
        cur_len = 0
        cur_start = None
        cur_end = None

    for seg in segments:
        text = seg["text"]
        if source_type == "audio":
            s_start, s_end = seg["startSec"], seg["endSec"]
        else:
            s_start, s_end = seg["page"], seg["page"]

        if cur_len + len(text) > max_chars and cur_texts:
            flush()

        if cur_start is None:
            cur_start = s_start
        cur_end = s_end
        cur_texts.append(text)
        cur_len += len(text) + 1

    flush()

    return {
        "documentId": document_id,
        "sourceType": source_type,
        "chunks": [
            {"chunkId": f"{document_id}#{i + 1:04d}", **c} for i, c in enumerate(chunks)
        ],
    }


def lambda_handler(event, context):
    user_id = event["userId"]
    document_id = event["documentId"]
    bucket = event.get("bucket", DEFAULT_BUCKET)
    text_key = event.get("textKey", f"processed/{user_id}/{document_id}/text.json")

    obj = s3.get_object(Bucket=bucket, Key=text_key)
    doc = json.loads(obj["Body"].read())

    result = make_chunks(doc, document_id)

    out_key = f"processed/{user_id}/{document_id}/chunks.json"
    s3.put_object(
        Bucket=bucket,
        Key=out_key,
        Body=json.dumps(result).encode(),
        ContentType="application/json",
    )

    return {"chunksKey": out_key, "chunkCount": len(result["chunks"])}
