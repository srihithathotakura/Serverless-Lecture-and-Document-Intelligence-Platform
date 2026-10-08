import json
import os

import boto3
import pypdf

BUCKET = os.environ["DATA_BUCKET"]
s3 = boto3.client("s3")

MAX_PAGES = 20
TMP_PATH = "/tmp/in.pdf"


def extract_segments(path_or_file):
    """Return [{text, page}] for every page with text. Raises with a user-readable message."""
    try:
        reader = pypdf.PdfReader(path_or_file)
        encrypted = reader.is_encrypted
    except Exception:
        raise Exception("Could not read PDF")
    if encrypted:
        raise Exception("PDF is encrypted")

    try:
        pages = list(reader.pages)
    except Exception:
        raise Exception("Could not read PDF")
    if len(pages) > MAX_PAGES:
        raise Exception("PDF has more than 20 pages")

    segments = []
    for number, page in enumerate(pages, start=1):
        try:
            text = " ".join((page.extract_text() or "").split())
        except Exception:
            raise Exception("Could not read PDF")
        if text:
            segments.append({"text": text, "page": number})
    if not segments:
        raise Exception("No text found. PDF may be scanned images")
    return segments


def lambda_handler(event, context):
    user_id, document_id = event["userId"], event["documentId"]
    bucket = event.get("bucket") or BUCKET
    s3.download_file(bucket, event["s3Key"], TMP_PATH)
    try:
        segments = extract_segments(TMP_PATH)
    finally:
        os.remove(TMP_PATH)

    text_key = f"processed/{user_id}/{document_id}/text.json"
    doc = {"documentId": document_id, "sourceType": "pdf", "segments": segments}
    s3.put_object(Bucket=bucket, Key=text_key, Body=json.dumps(doc, ensure_ascii=False).encode(),
                  ContentType="application/json")
    return {"textKey": text_key, "segmentCount": len(segments)}
