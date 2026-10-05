import json

import pytest
from m1_helpers import BUCKET, load


def s3_event(key, size=1000, bucket=BUCKET):
    return {"source": "aws.s3", "detail-type": "Object Created",
            "detail": {"bucket": {"name": bucket}, "object": {"key": key, "size": size}}}


def put_item(table, doc="d1", status="UPLOADING", **extra):
    table.put_item(Item={"userId": "user-A", "documentId": doc, "status": status, **extra})


def get_item(table, doc="d1"):
    return table.get_item(Key={"userId": "user-A", "documentId": doc}).get("Item")


# ---------- parse-event ----------

def test_parse_event_audio(aws):
    _, table = aws
    put_item(table)
    out = load("parse_event").lambda_handler(s3_event("uploads/user-A/d1/talk.wav"), None)
    assert out == {"skip": False, "userId": "user-A", "documentId": "d1", "bucket": BUCKET,
                   "s3Key": "uploads/user-A/d1/talk.wav", "fileName": "talk.wav", "fileType": "audio"}
    item = get_item(table)
    assert item["status"] == "PROCESSING"
    assert item["step"] == "TRANSCRIBING"
    assert item["startedAt"].endswith("Z")


def test_parse_event_pdf_step(aws):
    _, table = aws
    put_item(table)
    out = load("parse_event").lambda_handler(s3_event("uploads/user-A/d1/notes.pdf"), None)
    assert out["fileType"] == "pdf"
    assert get_item(table)["step"] == "EXTRACTING"


def test_parse_event_duplicate_is_skipped(aws):
    _, table = aws
    put_item(table)
    fn = load("parse_event")
    assert fn.lambda_handler(s3_event("uploads/user-A/d1/talk.wav"), None)["skip"] is False
    assert fn.lambda_handler(s3_event("uploads/user-A/d1/talk.wav"), None) == {"skip": True}


def test_parse_event_without_item_is_skipped(aws):
    _, table = aws
    assert load("parse_event").lambda_handler(s3_event("uploads/user-A/d1/talk.wav"), None) == {"skip": True}
    assert get_item(table) is None  # never creates an item


@pytest.mark.parametrize("key", ["uploads/user-A/talk.wav", "other/user-A/d1/talk.wav", "uploads/user-A/d1/x/a.wav"])
def test_parse_event_bad_key_is_skipped(aws, key):
    assert load("parse_event").lambda_handler(s3_event(key), None) == {"skip": True}


def test_parse_event_bad_extension_fails_item(aws):
    _, table = aws
    put_item(table)
    assert load("parse_event").lambda_handler(s3_event("uploads/user-A/d1/talk.mp3"), None) == {"skip": True}
    item = get_item(table)
    assert item["status"] == "FAILED"
    assert item["errorMessage"] == "Unsupported file type. Use WAV audio or PDF"


def test_parse_event_too_big_fails_item(aws):
    _, table = aws
    put_item(table)
    event = s3_event("uploads/user-A/d1/talk.wav", size=100 * 1024 * 1024 + 1)
    assert load("parse_event").lambda_handler(event, None) == {"skip": True}
    assert get_item(table)["status"] == "FAILED"


# ---------- update-status ----------

def test_update_status_step(aws):
    _, table = aws
    put_item(table, status="PROCESSING", step="TRANSCRIBING")
    out = load("update_status").lambda_handler(
        {"userId": "user-A", "documentId": "d1", "status": "PROCESSING", "step": "CHUNKING"}, None)
    assert out == {"ok": True}
    item = get_item(table)
    assert item["step"] == "CHUNKING"
    assert item["updatedAt"].endswith("Z")


def test_update_status_done(aws):
    _, table = aws
    put_item(table, status="PROCESSING", step="INDEXING", startedAt="2026-01-01T00:00:00Z")
    load("update_status").lambda_handler({"userId": "user-A", "documentId": "d1", "status": "DONE",
                                          "summary": "A short summary.", "chunkCount": 4}, None)
    item = get_item(table)
    assert item["status"] == "DONE"
    assert "step" not in item
    assert item["summary"] == "A short summary."
    assert item["chunkCount"] == 4
    assert item["processingMs"] > 0


def test_update_status_failed_parses_lambda_cause(aws):
    _, table = aws
    put_item(table, status="PROCESSING", step="TRANSCRIBING")
    cause = json.dumps({"errorMessage": "Audio longer than 5 minutes", "errorType": "Exception",
                        "stackTrace": ["  File ..."]})
    load("update_status").lambda_handler(
        {"userId": "user-A", "documentId": "d1", "status": "FAILED", "errorMessage": cause}, None)
    item = get_item(table)
    assert item["status"] == "FAILED"
    assert item["errorMessage"] == "Audio longer than 5 minutes"
    assert "step" not in item


def test_update_status_error_truncated_and_plain():
    fn = load("update_status")
    assert fn.clean_error("x" * 500) == "x" * 300
    assert fn.clean_error("{not json") == "{not json"
    assert fn.clean_error(None) == "Processing failed"


def test_update_status_never_recreates_deleted_item(aws):
    _, table = aws
    with pytest.raises(Exception, match="no longer exists"):
        load("update_status").lambda_handler(
            {"userId": "user-A", "documentId": "gone", "status": "PROCESSING", "step": "CHUNKING"}, None)
    assert get_item(table, "gone") is None


def test_update_status_rejects_unknown_status():
    with pytest.raises(Exception, match="Invalid status"):
        load("update_status").lambda_handler({"userId": "u", "documentId": "d", "status": "WEIRD"}, None)
