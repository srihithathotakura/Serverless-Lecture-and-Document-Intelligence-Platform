import json
import os

import boto3
from moto import mock_aws

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def load_fixture(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return json.load(f)


def make_sample_chunks_doc(index_app):
    doc = load_fixture("text-audio.json")
    # Build a minimal chunks doc directly (index doesn't depend on chunk module)
    return {
        "documentId": doc["documentId"],
        "chunks": [
            {"chunkId": "c0000", "text": "Photosynthesis converts light energy into chemical energy."},
            {"chunkId": "c0001", "text": "The Calvin cycle fixes carbon dioxide into glucose."},
        ],
    }


def test_tokenize_removes_stopwords_and_short_words(index_app):
    tokens = index_app.tokenize("What is the Calvin cycle and how does it work?")
    assert "the" not in tokens
    assert "is" not in tokens
    assert "calvin" in tokens
    assert "cycle" in tokens


def test_build_index_maps_words_to_chunks(index_app):
    chunks_doc = make_sample_chunks_doc(index_app)
    result = index_app.build_index(chunks_doc)

    assert result["documentId"] == chunks_doc["documentId"]
    assert "photosynthesis" in result["index"]
    assert "c0000" in result["index"]["photosynthesis"]
    assert "calvin" in result["index"]
    assert "c0001" in result["index"]["calvin"]


@mock_aws
def test_lambda_handler_writes_index_to_s3(index_app):
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-bucket")

    chunks_doc = make_sample_chunks_doc(index_app)
    s3.put_object(
        Bucket="test-bucket",
        Key="processed/u1/d1/chunks.json",
        Body=json.dumps(chunks_doc).encode(),
    )

    result = index_app.lambda_handler({"userId": "u1", "documentId": "d1"}, None)

    assert result["indexKey"] == "processed/u1/d1/index.json"
    assert result["chunkCount"] == 2

    obj = s3.get_object(Bucket="test-bucket", Key="processed/u1/d1/index.json")
    written = json.loads(obj["Body"].read())
    assert "photosynthesis" in written["index"]
