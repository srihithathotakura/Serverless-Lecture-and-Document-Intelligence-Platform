"""Write docs/perf/pipeline-timings.csv from DONE items in your dev account (Doc 1, week 5 step 3).

Usage (from the repo root, AWS_PROFILE pointing at your own dev account):
    python pipeline/scripts/pipeline_timings.py --stage dev --user <cognito-sub-or-test-user>

Reads processingMs from DynamoDB and the length (audio minutes or PDF pages) from text.json.
"""
import argparse
import csv
import json
from pathlib import Path

import boto3
from boto3.dynamodb.conditions import Key

OUT = Path(__file__).resolve().parents[2] / "docs" / "perf" / "pipeline-timings.csv"


def length_of(s3, bucket, user_id, document_id):
    key = f"processed/{user_id}/{document_id}/text.json"
    doc = json.loads(s3.get_object(Bucket=bucket, Key=key)["Body"].read())
    segments = doc["segments"]
    if doc["sourceType"] == "audio":
        return round(max(s["endSec"] for s in segments) / 60, 1)
    return max(s["page"] for s in segments)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", default="dev")
    parser.add_argument("--user", required=True, help="userId (Cognito sub) that uploaded the test files")
    args = parser.parse_args()

    account = boto3.client("sts").get_caller_identity()["Account"]
    bucket = f"lecdoc-{args.stage}-data-{account}"
    table = boto3.resource("dynamodb").Table(f"lecdoc-{args.stage}-documents")
    s3 = boto3.client("s3")

    items = table.query(KeyConditionExpression=Key("userId").eq(args.user))["Items"]
    rows = []
    for item in items:
        if item.get("status") != "DONE" or "processingMs" not in item:
            continue
        length = length_of(s3, bucket, args.user, item["documentId"])
        rows.append((item["fileType"], length, round(int(item["processingMs"]) / 1000, 1)))
    rows.sort()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["fileType", "lengthMinOrPages", "processingSec"])
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {OUT}")


if __name__ == "__main__":
    main()
