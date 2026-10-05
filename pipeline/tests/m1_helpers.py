"""Shared helpers for pipeline tests. No real AWS or model calls: moto mocks S3 and DynamoDB."""
import importlib.util
import io
import math
import os
import struct
import wave
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
BUCKET = "lecdoc-test-data-123456789012"
TABLE = "lecdoc-test-documents"

os.environ.update({
    "AWS_ACCESS_KEY_ID": "testing", "AWS_SECRET_ACCESS_KEY": "testing", "AWS_SESSION_TOKEN": "testing",
    "AWS_DEFAULT_REGION": "us-east-1", "STAGE": "test", "DATA_BUCKET": BUCKET, "DOCUMENTS_TABLE": TABLE,
    "MANTLE_BASE_URL": "https://mantle.example/v1", "STT_MODEL_ID": "test-stt-model",
    "BEDROCK_KEY_PARAM": "/lecdoc/test/bedrock-api-key",
})


def load(name):
    """Import pipeline/src/<name>/app.py fresh, so module-level boto3 clients are created inside the mock."""
    spec = importlib.util.spec_from_file_location(f"{name}_app", SRC / name / "app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def api_event(user_id, body=None, document_id=None):
    event = {"requestContext": {"authorizer": {"jwt": {"claims": {"sub": user_id}}}}}
    if body is not None:
        event["body"] = body
    if document_id is not None:
        event["pathParameters"] = {"documentId": document_id}
    return event


def make_wav(seconds, rate=16000, channels=1, width=2):
    """A 440 Hz tone as WAV bytes."""
    frames = int(seconds * rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        one = bytearray()
        for i in range(rate):  # one second, repeated
            sample = int(8000 * math.sin(2 * math.pi * 440 * i / rate))
            packed = struct.pack("<h", sample) if width == 2 else bytes([128 + sample // 256])
            one += packed * channels
        full, rest = divmod(frames, rate)
        w.writeframes(bytes(one) * full + bytes(one[: rest * channels * width]))
    return buf.getvalue()


def make_pdf(pages):
    """A minimal text PDF. pages is a list of strings; an empty string gives a page without text."""
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", None,
               "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for text in pages:
        safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 12 Tf 72 720 Td ({safe}) Tj ET" if text else ""
        objects.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
        content_ref = len(objects)
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                       f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_ref} 0 R >>")
        kids.append(f"{len(objects)} 0 R")
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"

    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for n, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n{obj}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)
