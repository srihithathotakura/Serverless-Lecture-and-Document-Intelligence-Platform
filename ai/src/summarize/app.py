import json
import os
import urllib.request

import boto3

s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
ssm = boto3.client("ssm", region_name=os.environ.get("AWS_REGION", "us-east-1"))
DEFAULT_BUCKET = os.environ.get("DATA_BUCKET")
TEXT_MODEL_ID = os.environ.get("TEXT_MODEL_ID", "google.gemma-3-4b-it")
MANTLE_BASE_URL = os.environ.get("MANTLE_BASE_URL", "https://bedrock-mantle.us-east-1.api.aws/v1")
BEDROCK_KEY_PARAM = os.environ.get("BEDROCK_KEY_PARAM")

_cached_key = None


class ThrottlingException(Exception):
    pass


def api_key():
    global _cached_key
    if _cached_key is None:
        resp = ssm.get_parameter(Name=BEDROCK_KEY_PARAM, WithDecryption=True)
        _cached_key = resp["Parameter"]["Value"]
    return _cached_key


def generate(instruction, text, max_tokens=300, timeout=60):
    body = {
        "model": TEXT_MODEL_ID,
        "max_tokens": max_tokens,
        "temperature": 0.2,
        "messages": [{"role": "user", "content": instruction + "\n\n" + text}],
    }
    req = urllib.request.Request(
        MANTLE_BASE_URL + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + api_key(), "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 429 or e.code >= 500:
            raise ThrottlingException(str(e))
        raise
    print(json.dumps({"event": "AI_USAGE", **out.get("usage", {})}))
    return out["choices"][0]["message"]["content"].strip()


def summarize_chunks(chunks_doc, max_tokens=300):
    full_text = " ".join(c["text"] for c in chunks_doc["chunks"])
    instruction = (
        "Summarize the following lecture content in plain text, at most 250 words, "
        "covering the key points."
    )
    return generate(instruction, full_text, max_tokens=max_tokens)


def lambda_handler(event, context):
    user_id = event["userId"]
    document_id = event["documentId"]
    bucket = event.get("bucket", DEFAULT_BUCKET)
    chunks_key = event.get("chunksKey", f"processed/{user_id}/{document_id}/chunks.json")

    obj = s3.get_object(Bucket=bucket, Key=chunks_key)
    chunks_doc = json.loads(obj["Body"].read())

    summary_text = summarize_chunks(chunks_doc)

    summary_key = f"processed/{user_id}/{document_id}/summary.txt"
    s3.put_object(
        Bucket=bucket,
        Key=summary_key,
        Body=summary_text.encode(),
        ContentType="text/plain",
    )

    return {"summary": summary_text}
