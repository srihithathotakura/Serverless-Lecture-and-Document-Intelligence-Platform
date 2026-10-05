import json
import os
import re
import urllib.error
import urllib.request
import uuid

import boto3

BUCKET = os.environ["DATA_BUCKET"]
s3 = boto3.client("s3")
_ssm = boto3.client("ssm")
_key = None


class ThrottlingException(Exception):
    pass


def api_key():
    global _key
    if _key is None:
        _key = _ssm.get_parameter(Name=os.environ["BEDROCK_KEY_PARAM"], WithDecryption=True)["Parameter"]["Value"]
    return _key


def call_model(path, body, content_type="application/json", timeout=50):
    """POST to the Bedrock OpenAI-compatible endpoint. body is a dict (sent as JSON) or raw bytes."""
    data = json.dumps(body).encode() if isinstance(body, dict) else body
    req = urllib.request.Request(os.environ["MANTLE_BASE_URL"] + path, data=data,
                                 headers={"Authorization": "Bearer " + api_key(), "Content-Type": content_type})
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


def multipart(fields, file_field, file_name, file_bytes, file_type):
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{file_name}"\r\n'
                 f"Content-Type: {file_type}\r\n\r\n".encode() + file_bytes + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def stt_transcribe(wav_bytes):
    """The one place that knows the speech request format. Must match infra/checks/check_stt.sh.

    OpenAI-compatible transcription: multipart POST /audio/transcriptions with file + model,
    response {"text": "..."}.
    """
    body, content_type = multipart({"model": os.environ["STT_MODEL_ID"], "response_format": "json"},
                                   "file", "window.wav", wav_bytes, "audio/wav")
    result = call_model("/audio/transcriptions", body, content_type=content_type)
    return result.get("text") or ""


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
