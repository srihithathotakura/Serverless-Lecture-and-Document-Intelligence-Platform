import json
import os
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

TABLE = boto3.resource("dynamodb").Table(os.environ["DOCUMENTS_TABLE"])


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
    items, kwargs = [], {"KeyConditionExpression": Key("userId").eq(user_id)}
    while True:
        page = TABLE.query(**kwargs)
        items.extend(page.get("Items", []))
        if "LastEvaluatedKey" not in page:
            break
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    items.sort(key=lambda i: i.get("createdAt", ""), reverse=True)
    return resp(200, {"documents": items})
