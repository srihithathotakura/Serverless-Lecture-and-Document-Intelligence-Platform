import os

import boto3

s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
polly = boto3.client("polly", region_name=os.environ.get("AWS_REGION", "us-east-1"))
BUCKET = os.environ.get("DATA_BUCKET")


def synthesize_speech(text, voice_id="Joanna"):
    response = polly.synthesize_speech(
        Text=text,
        OutputFormat="mp3",
        VoiceId=voice_id,
    )
    return response["AudioStream"].read()


def lambda_handler(event, context):
    user_id = event["userId"]
    document_id = event["documentId"]
    text = event["text"]
    voice_id = event.get("voiceId", "Joanna")

    audio_bytes = synthesize_speech(text, voice_id=voice_id)

    out_key = f"processed/{user_id}/{document_id}/speech-{voice_id}.mp3"
    s3.put_object(
        Bucket=BUCKET,
        Key=out_key,
        Body=audio_bytes,
        ContentType="audio/mpeg",
    )

    return {"audioKey": out_key, "bytes": len(audio_bytes)}
