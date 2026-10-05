import json
import os
import re

import boto3

BUCKET = os.environ["DATA_BUCKET"]
s3 = boto3.client("s3")

MIN_WORDS = 2


def clean(text):
    text = (text or "").replace("(...)", " ")
    return re.sub(r"\s+", " ", text).strip()


def build_segments(windows):
    segments = []
    for w in sorted(windows, key=lambda w: w["startSec"]):
        text = clean(w.get("text"))
        if len(text.split()) < MIN_WORDS:
            continue
        segments.append({"text": text, "startSec": float(w["startSec"]), "endSec": float(w["endSec"])})
    return segments


def lambda_handler(event, context):
    user_id, document_id = event["userId"], event["documentId"]
    bucket = event.get("bucket") or BUCKET

    segments = build_segments(event.get("windows") or [])
    if not segments:
        raise Exception("No speech detected in audio")

    text_key = f"processed/{user_id}/{document_id}/text.json"
    doc = {"documentId": document_id, "sourceType": "audio", "segments": segments}
    s3.put_object(Bucket=bucket, Key=text_key, Body=json.dumps(doc, ensure_ascii=False).encode(),
                  ContentType="application/json")
    return {"textKey": text_key, "segmentCount": len(segments)}
