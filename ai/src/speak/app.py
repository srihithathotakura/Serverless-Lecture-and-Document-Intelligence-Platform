import os
import boto3

s3 = boto3.client("s3")
polly = boto3.client("polly")
BUCKET = os.environ.get("DATA_BUCKET")


def synthesize_speech(text, voice_id="Joanna"):
    response = polly.synthesize_speech(
        Text=text,
        OutputFormat="mp3",
        VoiceId=voice_id,
    )
    return response["AudioStream"].read()


def lambda_handler(event, context):
    document_id = event["documentId"]
    text = event["text"]
    voice_id = event.get("voiceId", "Joanna")

    audio_bytes = synthesize_speech(text, voice_id=voice_id)

    out_key = f"documents/{document_id}/speech-{voice_id}.mp3"
    s3.put_object(
        Bucket=BUCKET,
        Key=out_key,
        Body=audio_bytes,
        ContentType="audio/mpeg",
    )

    return {"status": "ok", "audioKey": out_key, "bytes": len(audio_bytes)}
