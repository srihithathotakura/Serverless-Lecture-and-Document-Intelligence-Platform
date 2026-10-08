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
    result = chunk_app.make_chunks(doc)

    assert result["documentId"] == doc["documentId"]
    assert result["sourceType"] == "audio"
    assert len(result["chunks"]) > 0
    for chunk in result["chunks"]:
        assert "startSec" in chunk
        assert "endSec" in chunk
        assert chunk["endSec"] >= chunk["startSec"]
        assert len(chunk["text"]) <= 600  # max_chars=500 plus one segment's slack


def test_make_chunks_pdf_preserves_page_ranges(chunk_app):
    doc = load_fixture("text-pdf.json")
    result = chunk_app.make_chunks(doc)

    assert result["sourceType"] == "pdf"
    for chunk in result["chunks"]:
        assert "startPage" in chunk
        assert "endPage" in chunk
        assert chunk["endPage"] >= chunk["startPage"]


def test_make_chunks_chunk_ids_sequential(chunk_app):
    doc = load_fixture("text-audio.json")
    result = chunk_app.make_chunks(doc)
    ids = [c["chunkId"] for c in result["chunks"]]
    assert ids == [f"c{i:04d}" for i in range(len(ids))]


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
    assert written["documentId"] == doc["documentId"]
    assert len(written["chunks"]) == result["chunkCount"]
