import json

import boto3
from moto import mock_aws


def sample_chunks_doc():
    return {
        "documentId": "doc1",
        "chunks": [
            {"chunkId": "c0000", "text": "Photosynthesis converts light energy into chemical energy."},
            {"chunkId": "c0001", "text": "The Calvin cycle fixes carbon dioxide into glucose."},
        ],
    }


def test_summarize_chunks_calls_generate_with_combined_text(summarize_app, monkeypatch):
    captured = {}

    def fake_generate(instruction, text, max_tokens=300):
        captured["instruction"] = instruction
        captured["text"] = text
        return "A short summary."

    monkeypatch.setattr(summarize_app, "generate", fake_generate)

    result = summarize_app.summarize_chunks(sample_chunks_doc())

    assert result == "A short summary."
    assert "Photosynthesis" in captured["text"]
    assert "Calvin cycle" in captured["text"]
    assert "summarize" in captured["instruction"].lower()


@mock_aws
def test_lambda_handler_returns_summary_field_only(summarize_app, monkeypatch):
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-bucket")
    s3.put_object(
        Bucket="test-bucket",
        Key="processed/u1/d1/chunks.json",
        Body=json.dumps(sample_chunks_doc()).encode(),
    )

    monkeypatch.setattr(summarize_app, "generate", lambda instruction, text, max_tokens=300: "Mock summary.")

    result = summarize_app.lambda_handler({"userId": "u1", "documentId": "d1"}, None)

    assert result == {"summary": "Mock summary."}


def test_api_key_fetches_from_ssm_and_caches(summarize_app, monkeypatch):
    calls = {"count": 0}

    class FakeSSM:
        def get_parameter(self, Name, WithDecryption):
            calls["count"] += 1
            return {"Parameter": {"Value": "secret-key-123"}}

    summarize_app.ssm = FakeSSM()
    summarize_app._cached_key = None

    key1 = summarize_app.api_key()
    key2 = summarize_app.api_key()

    assert key1 == "secret-key-123"
    assert key2 == "secret-key-123"
    assert calls["count"] == 1  # cached after first call
