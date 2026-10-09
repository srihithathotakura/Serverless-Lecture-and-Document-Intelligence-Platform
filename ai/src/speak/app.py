import json
import os

import boto3

s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
polly = boto3.client("polly", region_name=os.environ.get("AWS_REGION", "us-east-1"))
DEFAULT_BUCKET = os.environ.get("DATA_BUCKET")


def synthesize_speech(text, voice_id="Joanna"):
    response = polly.synthesize_speech(
        Text=text,
        OutputFormat="mp3",
        VoiceId=voice_id,
    )
    return response["AudioStream"].read()


def parse_request(event):
    if "body" in event:
        body = event["body"]
        payload = json.loads(body) if isinstance(body, str) else body
    else:
        payload = event
    return payload.get("documentId")


def lambda_handler(event, context):
    user_id = event.get("userId") or (event.get("requestContext", {}).get("authorizer", {}).get("jwt", {}).get("claims", {}).get("sub"))
    document_id = parse_request(event)

    if not document_id:
        return {"error": "documentId is required"}

    bucket = event.get("bucket", DEFAULT_BUCKET)
    summary_key = f"processed/{user_id}/{document_id}/summary.txt"

    try:
        obj = s3.get_object(Bucket=bucket, Key=summary_key)
    except s3.exceptions.NoSuchKey:
        return {"error": "no summary exists for this document"}

    text = obj["Body"].read().decode()

    audio_bytes = synthesize_speech(text)

    audio_key = f"processed/{user_id}/{document_id}/summary.mp3"
    s3.put_object(
        Bucket=bucket,
        Key=audio_key,
        Body=audio_bytes,
        ContentType="audio/mpeg",
    )

    audio_url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": audio_key},
        ExpiresIn=900,
    )

    return {"audioUrl": audio_url, "expiresIn": 900}
