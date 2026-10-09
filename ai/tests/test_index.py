import json

import boto3
from moto import mock_aws


def sample_chunks_doc():
    return {
        "documentId": "doc1",
        "sourceType": "audio",
        "chunks": [
            {
                "chunkId": "doc1#0001",
                "text": "Photosynthesis converts light energy into chemical energy.",
                "startSec": 0.0,
                "endSec": 30.0,
                "pageStart": None,
                "pageEnd": None,
            },
            {
                "chunkId": "doc1#0002",
                "text": "The Calvin cycle fixes carbon dioxide into glucose.",
                "startSec": 30.0,
                "endSec": 60.0,
                "pageStart": None,
                "pageEnd": None,
            },
        ],
    }


def test_tokenize_removes_stopwords_and_short_words(index_app):
    tokens = index_app.tokenize("What is the Calvin cycle and how does it work?")
    assert "the" not in tokens
    assert "is" not in tokens
    assert "calvin" in tokens
    assert "cycle" in tokens


def test_build_index_produces_tfidf_shape(index_app):
    chunks_doc = sample_chunks_doc()
    result = index_app.build_index(chunks_doc, "lecture1.wav")

    assert result["documentId"] == "doc1"
    assert result["fileName"] == "lecture1.wav"
    assert result["sourceType"] == "audio"
    assert result["method"] == "tfidf-v1"
    assert len(result["chunks"]) == 2

    c0 = result["chunks"][0]
    assert c0["chunkId"] == "doc1#0001"
    assert c0["startSec"] == 0.0
    assert c0["endSec"] == 30.0
    assert c0["pageStart"] is None
    assert "photosynthesis" in c0["tf"]
    assert c0["tf"]["photosynthesis"] == 1

    c1 = result["chunks"][1]
    assert "calvin" in c1["tf"]
    assert "cycle" in c1["tf"]


@mock_aws
def test_lambda_handler_writes_index_to_s3(index_app):
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-bucket")

    chunks_doc = sample_chunks_doc()
    s3.put_object(
        Bucket="test-bucket",
        Key="processed/u1/d1/chunks.json",
        Body=json.dumps(chunks_doc).encode(),
    )

    result = index_app.lambda_handler(
        {"userId": "u1", "documentId": "d1", "fileName": "lecture1.wav"}, None
    )

    assert result["indexKey"] == "processed/u1/d1/index.json"
    assert result["chunkCount"] == 2

    obj = s3.get_object(Bucket="test-bucket", Key="processed/u1/d1/index.json")
    written = json.loads(obj["Body"].read())
    assert written["method"] == "tfidf-v1"
    assert written["fileName"] == "lecture1.wav"
    assert "photosynthesis" in written["chunks"][0]["tf"]


@mock_aws
def test_lambda_handler_defaults_filename_when_missing(index_app):
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-bucket")

    chunks_doc = sample_chunks_doc()
    s3.put_object(
        Bucket="test-bucket",
        Key="processed/u1/d1/chunks.json",
        Body=json.dumps(chunks_doc).encode(),
    )

    result = index_app.lambda_handler({"userId": "u1", "documentId": "d1"}, None)
    assert result["indexKey"] == "processed/u1/d1/index.json"
