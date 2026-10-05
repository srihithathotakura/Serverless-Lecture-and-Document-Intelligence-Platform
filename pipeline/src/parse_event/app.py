import json
import os
from datetime import UTC, datetime
from urllib.parse import unquote_plus

import boto3

TABLE = boto3.resource("dynamodb").Table(os.environ["DOCUMENTS_TABLE"])

FILE_TYPES = {"wav": "audio", "pdf": "pdf"}
FIRST_STEP = {"audio": "TRANSCRIBING", "pdf": "EXTRACTING"}
MAX_BYTES = 100 * 1024 * 1024
SKIP = {"skip": True}


def now_iso():
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_conditional_fail(err):
    return getattr(err, "response", {}).get("Error", {}).get("Code") == "ConditionalCheckFailedException"


def fail_item(user_id, document_id, message):
    """Mark an UPLOADING item FAILED. Ignored when the item is missing or already moved on."""
    now = now_iso()
    try:
        TABLE.update_item(
            Key={"userId": user_id, "documentId": document_id},
            UpdateExpression="SET #status = :failed, errorMessage = :msg, updatedAt = :now",
            ConditionExpression="#status = :uploading",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={":failed": "FAILED", ":msg": message, ":now": now, ":uploading": "UPLOADING"},
        )
    except Exception as e:
        if not is_conditional_fail(e):
            raise


def lambda_handler(event, context):
    detail = event.get("detail") or {}
    bucket = (detail.get("bucket") or {}).get("name")
    obj = detail.get("object") or {}
    key = unquote_plus(obj.get("key") or "")

    parts = key.split("/")
    if not bucket or len(parts) != 4 or parts[0] != "uploads" or not all(parts[1:]):
        print(json.dumps({"event": "SKIP_BAD_KEY", "key": key}))
        return SKIP
    _, user_id, document_id, file_name = parts

    ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    file_type = FILE_TYPES.get(ext)
    if file_type is None:
        fail_item(user_id, document_id, "Unsupported file type. Use WAV audio or PDF")
        return SKIP
    if int(obj.get("size") or 0) > MAX_BYTES:
        fail_item(user_id, document_id, "File larger than 100 MB")
        return SKIP

    now = now_iso()
    try:
        # Conditional update: a duplicate EventBridge delivery or a file without an item is skipped
        TABLE.update_item(
            Key={"userId": user_id, "documentId": document_id},
            UpdateExpression="SET #status = :processing, #step = :step, startedAt = :now, updatedAt = :now",
            ConditionExpression="#status = :uploading",
            ExpressionAttributeNames={"#status": "status", "#step": "step"},
            ExpressionAttributeValues={":processing": "PROCESSING", ":step": FIRST_STEP[file_type],
                                       ":now": now, ":uploading": "UPLOADING"},
        )
    except Exception as e:
        if is_conditional_fail(e):
            print(json.dumps({"event": "SKIP_NOT_UPLOADING", "documentId": document_id}))
            return SKIP
        raise

    return {"skip": False, "userId": user_id, "documentId": document_id, "bucket": bucket,
            "s3Key": key, "fileName": file_name, "fileType": file_type}
