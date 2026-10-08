import json
import os
from decimal import Decimal

import boto3

TABLE = boto3.resource("dynamodb").Table(os.environ["DOCUMENTS_TABLE"])
BUCKET = os.environ["DATA_BUCKET"]
s3 = boto3.client("s3")


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


def delete_prefix(prefix):
    """Delete every object under prefix. Returns the number of objects deleted."""
    count = 0
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=prefix):
        keys = [{"Key": o["Key"]} for o in page.get("Contents", [])]
        if keys:
            # list_objects_v2 pages hold at most 1000 keys, the delete_objects limit
            result = s3.delete_objects(Bucket=BUCKET, Delete={"Objects": keys, "Quiet": True})
            if result.get("Errors"):
                raise Exception(f"Could not delete {len(result['Errors'])} objects under {prefix}")
            count += len(keys)
    return count


def lambda_handler(event, context):
    user_id = get_user_id(event)
    document_id = (event.get("pathParameters") or {}).get("documentId")
    if not document_id:
        return resp(400, {"error": "documentId is required"})

    key = {"userId": user_id, "documentId": document_id}
    if "Item" not in TABLE.get_item(Key=key):
        return resp(404, {"error": "Document not found"})

    # S3 first: if this fails the item stays, so the user can retry the delete
    deleted = 0
    for root in ("uploads", "processed"):
        deleted += delete_prefix(f"{root}/{user_id}/{document_id}/")
    TABLE.delete_item(Key=key)

    print(json.dumps({"event": "DOCUMENT_DELETED", "documentId": document_id, "objects": deleted}))
    return resp(200, {"deleted": True})
