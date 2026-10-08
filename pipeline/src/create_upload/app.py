import base64
import json
import os
import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import boto3
from botocore.config import Config

TABLE = boto3.resource("dynamodb").Table(os.environ["DOCUMENTS_TABLE"])
BUCKET = os.environ["DATA_BUCKET"]
s3 = boto3.client("s3", region_name="us-east-1", config=Config(signature_version="s3v4"))

FILE_TYPES = {"wav": "audio", "pdf": "pdf"}
EXPIRES_IN = 900
MAX_NAME = 100


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


def now_iso():
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def extension(name):
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def sanitize(name, ext):
    """Characters outside A-Za-z0-9._- become _, max 100 chars. Keeps the extension when truncating."""
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    if len(safe) > MAX_NAME:
        safe = safe[:MAX_NAME - len(ext) - 1] + "." + ext
    return safe


def parse_body(event):
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode()
    body = json.loads(raw)
    if not isinstance(body, dict):
        raise TypeError
    return body


def lambda_handler(event, context):
    user_id = get_user_id(event)
    try:
        body = parse_body(event)
    except (ValueError, TypeError):
        return resp(400, {"error": "Request body must be a JSON object"})

    file_name = body.get("fileName")
    content_type = body.get("contentType")
    if not isinstance(file_name, str) or not file_name.strip():
        return resp(400, {"error": "fileName is required"})
    if not isinstance(content_type, str) or not content_type or len(content_type) > 100:
        return resp(400, {"error": "contentType must be a non-empty string of at most 100 characters"})

    ext = extension(file_name)
    file_type = FILE_TYPES.get(ext)
    if file_type is None:
        return resp(400, {"error": "Unsupported file type. Use WAV audio or PDF"})

    document_id = uuid.uuid4().hex
    safe_name = sanitize(file_name.strip(), ext)
    s3_key = f"uploads/{user_id}/{document_id}/{safe_name}"
    now = now_iso()

    TABLE.put_item(Item={
        "userId": user_id,
        "documentId": document_id,
        "fileName": safe_name,
        "contentType": content_type,
        "s3Key": s3_key,
        "fileType": file_type,
        "status": "UPLOADING",
        "createdAt": now,
        "updatedAt": now,
    })

    upload_url = s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": BUCKET, "Key": s3_key, "ContentType": content_type},
        ExpiresIn=EXPIRES_IN,
    )
    return resp(200, {"documentId": document_id, "uploadUrl": upload_url, "s3Key": s3_key, "expiresIn": EXPIRES_IN})
