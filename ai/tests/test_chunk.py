import json
import os

import boto3
from moto import mock_aws

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def load_fixture(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return json.load(f)


def test_make_chunks_audio_preserves_time_ranges(chunk_app):
    doc = load_fixture("text-audio.json")
    result = chunk_app.make_chunks(doc, "docA")

    assert result["documentId"] == "docA"
    assert result["sourceType"] == "audio"
    assert len(result["chunks"]) > 0
    for chunk in result["chunks"]:
        assert chunk["startSec"] is not None
        assert chunk["endSec"] is not None
        assert chunk["pageStart"] is None
        assert chunk["pageEnd"] is None
        assert chunk["endSec"] >= chunk["startSec"]
        assert len(chunk["text"]) <= 600


def test_make_chunks_pdf_preserves_page_ranges(chunk_app):
    doc = load_fixture("text-pdf.json")
    result = chunk_app.make_chunks(doc, "docB")

    assert result["sourceType"] == "pdf"
    for chunk in result["chunks"]:
        assert chunk["pageStart"] is not None
        assert chunk["pageEnd"] is not None
        assert chunk["startSec"] is None
        assert chunk["endSec"] is None
        assert chunk["pageEnd"] >= chunk["pageStart"]


def test_make_chunks_chunk_ids_sequential(chunk_app):
    doc = load_fixture("text-audio.json")
    result = chunk_app.make_chunks(doc, "docC")
    ids = [c["chunkId"] for c in result["chunks"]]
    assert ids == [f"docC#{i + 1:04d}" for i in range(len(ids))]


@mock_aws
def test_lambda_handler_writes_chunks_to_s3(chunk_app):
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-bucket")

    doc = load_fixture("text-audio.json")
    s3.put_object(
        Bucket="test-bucket",
        Key="processed/u1/d1/text.json",
        Body=json.dumps(doc).encode(),
    )

    result = chunk_app.lambda_handler({"userId": "u1", "documentId": "d1"}, None)

    assert result["chunksKey"] == "processed/u1/d1/chunks.json"
    assert result["chunkCount"] > 0

    obj = s3.get_object(Bucket="test-bucket", Key="processed/u1/d1/chunks.json")
    written = json.loads(obj["Body"].read())
    assert written["documentId"] == "d1"
    assert len(written["chunks"]) == result["chunkCount"]
    assert written["chunks"][0]["chunkId"] == "d1#0001"


@mock_aws
def test_lambda_handler_uses_bucket_from_event(chunk_app):
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="other-bucket")

    doc = load_fixture("text-audio.json")
    s3.put_object(
        Bucket="other-bucket",
        Key="processed/u1/d1/text.json",
        Body=json.dumps(doc).encode(),
    )

    result = chunk_app.lambda_handler(
        {"userId": "u1", "documentId": "d1", "bucket": "other-bucket"}, None
    )

    assert result["chunksKey"] == "processed/u1/d1/chunks.json"
