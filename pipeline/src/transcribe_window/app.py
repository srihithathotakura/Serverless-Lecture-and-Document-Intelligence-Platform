import base64
import json
import os
import re
import urllib.error
import urllib.request

import boto3

BUCKET = os.environ["DATA_BUCKET"]
s3 = boto3.client("s3")
_ssm = boto3.client("ssm")
_key = None

# Without the language the model sometimes answers in another language (seen with samples/audio-1min.wav)
STT_PROMPT = "Transcribe this English audio exactly, in English. Do not translate. Output only the transcript."
STT_MAX_TOKENS = 400


class ThrottlingException(Exception):
    pass


def api_key():
    global _key
    if _key is None:
        _key = _ssm.get_parameter(Name=os.environ["BEDROCK_KEY_PARAM"], WithDecryption=True)["Parameter"]["Value"]
    return _key


def call_model(path, body, timeout=50):
    req = urllib.request.Request(os.environ["MANTLE_BASE_URL"] + path, data=json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + api_key(), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code in (429, 500, 502, 503, 504):
            raise ThrottlingException(f"Model endpoint busy ({e.code})")
        if e.code in (401, 403):
            raise Exception("Bedrock API key rejected. Check the key in SSM")
        raise Exception(f"Model call failed ({e.code})")
    except (urllib.error.URLError, TimeoutError):
        raise ThrottlingException("Model endpoint unreachable or slow")


def stt_transcribe(wav_bytes):
    """The one place that knows the speech request format. Copied from infra/checks/check_stt.sh.

    Chat completions with the WAV as base64 input_audio plus a transcribe instruction,
    transcript in choices[0].message.content.
    """
    body = {"model": os.environ["STT_MODEL_ID"], "max_tokens": STT_MAX_TOKENS,
            "messages": [{"role": "user", "content": [
                {"type": "input_audio", "input_audio": {"data": base64.b64encode(wav_bytes).decode(), "format": "wav"}},
                {"type": "text", "text": STT_PROMPT}]}]}
    result = call_model("/chat/completions", body)
    choices = result.get("choices") or [{}]
    return (choices[0].get("message") or {}).get("content") or ""


def clean(text):
    text = (text or "").replace("(...)", " ")
    return re.sub(r"\s+", " ", text).strip()


def lambda_handler(event, context):
    win = event["window"]
    prefix = f"processed/{event['userId']}/{event['documentId']}/"
    if not win["key"].startswith(prefix):
        raise Exception("Window key does not belong to this document")
    bucket = event.get("bucket") or BUCKET

    wav_bytes = s3.get_object(Bucket=bucket, Key=win["key"])["Body"].read()
    text = clean(stt_transcribe(wav_bytes))
    print(json.dumps({"event": "STT_USAGE", "seconds": round(win["endSec"] - win["startSec"], 1)}))
    return {"startSec": win["startSec"], "endSec": win["endSec"], "text": text}
