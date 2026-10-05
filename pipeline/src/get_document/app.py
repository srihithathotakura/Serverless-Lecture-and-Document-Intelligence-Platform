import json
import os
from decimal import Decimal

import boto3
from botocore.config import Config

TABLE = boto3.resource("dynamodb").Table(os.environ["DOCUMENTS_TABLE"])
BUCKET = os.environ["DATA_BUCKET"]
s3 = boto3.client("s3", region_name="us-east-1", config=Config(signature_version="s3v4"))

EXPIRES_IN = 900


def get_user_id(event):
    return event["requestContext"]["authorizer"]["jwt"]["claims"]["sub"]


def _enc(o):
    if isinstance(o, Decimal):
        return int(o) if o % 1 == 0 else float(o)
    raise TypeError


def resp(status, body):
    return {"statusCode": status,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(body, default=_enc)}


def lambda_handler(event, context):
    user_id = get_user_id(event)
    document_id = (event.get("pathParameters") or {}).get("documentId")
    if not document_id:
        return resp(400, {"error": "documentId is required"})

    item = TABLE.get_item(Key={"userId": user_id, "documentId": document_id}).get("Item")
    if item is None:
        return resp(404, {"error": "Document not found"})

    body = {"document": item}
    if item.get("status") == "DONE":
        body["textUrl"] = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": BUCKET, "Key": f"processed/{user_id}/{document_id}/text.json"},
            ExpiresIn=EXPIRES_IN,
        )
    return resp(200, body)
