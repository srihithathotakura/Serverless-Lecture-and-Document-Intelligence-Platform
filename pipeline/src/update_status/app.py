import json
import os
from datetime import UTC, datetime

import boto3

TABLE = boto3.resource("dynamodb").Table(os.environ["DOCUMENTS_TABLE"])

STATUSES = {"UPLOADING", "PROCESSING", "DONE", "FAILED"}
FINAL = {"DONE", "FAILED"}
MAX_ERROR = 300
ISO = "%Y-%m-%dT%H:%M:%SZ"


def clean_error(message):
    """The state machine passes the raw error Cause. For a Lambda error it is a JSON string."""
    message = str(message or "").strip()
    if message.startswith("{"):
        try:
            parsed = json.loads(message)
            if isinstance(parsed, dict) and parsed.get("errorMessage"):
                message = str(parsed["errorMessage"])
        except ValueError:
            pass
    return (message or "Processing failed")[:MAX_ERROR]


def lambda_handler(event, context):
    status = event.get("status")
    if status not in STATUSES:
        raise Exception(f"Invalid status: {status}")
    key = {"userId": event["userId"], "documentId": event["documentId"]}
    now = datetime.now(UTC)

    sets = ["#status = :status", "updatedAt = :now"]
    removes = []
    names = {"#status": "status"}
    values = {":status": status, ":now": now.strftime(ISO)}

    if status in FINAL:
        removes.append("#step")
        names["#step"] = "step"
    elif event.get("step"):
        sets.append("#step = :step")
        names["#step"] = "step"
        values[":step"] = event["step"]

    if event.get("summary") is not None:
        sets.append("summary = :summary")
        values[":summary"] = str(event["summary"])
    if event.get("chunkCount") is not None:
        sets.append("chunkCount = :chunkCount")
        values[":chunkCount"] = int(event["chunkCount"])
    if status == "FAILED":
        sets.append("errorMessage = :err")
        values[":err"] = clean_error(event.get("errorMessage"))

    if status == "DONE":
        item = TABLE.get_item(Key=key, ProjectionExpression="startedAt").get("Item") or {}
        if item.get("startedAt"):
            started = datetime.strptime(item["startedAt"], ISO).replace(tzinfo=UTC)
            sets.append("processingMs = :ms")
            values[":ms"] = int((now - started).total_seconds() * 1000)

    expr = "SET " + ", ".join(sets)
    if removes:
        expr += " REMOVE " + ", ".join(removes)
    try:
        TABLE.update_item(Key=key, UpdateExpression=expr, ConditionExpression="attribute_exists(userId)",
                          ExpressionAttributeNames=names, ExpressionAttributeValues=values)
    except Exception as e:
        if getattr(e, "response", {}).get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            # The user deleted the document while it was processing. Never recreate the item
            raise Exception("Document no longer exists")
        raise
    return {"ok": True}
