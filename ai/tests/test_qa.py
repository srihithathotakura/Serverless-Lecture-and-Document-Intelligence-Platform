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


def build_index_doc(qa_app, chunks_doc):
    from collections import defaultdict
    inverted = defaultdict(set)
    for chunk in chunks_doc["chunks"]:
        for word in qa_app.tokenize(chunk["text"]):
            inverted[word].add(chunk["chunkId"])
    return {"documentId": chunks_doc["documentId"], "index": {w: sorted(ids) for w, ids in inverted.items()}}


def test_search_ranks_relevant_chunks_first(qa_app):
    chunks_doc = sample_chunks_doc()
    index_doc = build_index_doc(qa_app, chunks_doc)

    result = qa_app.search(index_doc, "What is the Calvin cycle?")

    assert "c0001" in result


def test_answer_question_builds_context_and_calls_generate(qa_app, monkeypatch):
    chunks_doc = sample_chunks_doc()
    index_doc = build_index_doc(qa_app, chunks_doc)

    captured = {}

    def fake_generate(instruction, text, max_tokens=200):
        captured["instruction"] = instruction
        return "The Calvin cycle fixes carbon dioxide."

    monkeypatch.setattr(qa_app, "generate", fake_generate)

    result = qa_app.answer_question(chunks_doc, index_doc, "What is the Calvin cycle?")

    assert result["question"] == "What is the Calvin cycle?"
    assert result["answer"] == "The Calvin cycle fixes carbon dioxide."
    assert "c0001" in result["sourceChunks"]
    assert "Calvin cycle" in captured["instruction"]


@mock_aws
def test_lambda_handler_reads_chunks_and_index_from_s3(qa_app, monkeypatch):
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-bucket")

    chunks_doc = sample_chunks_doc()
    index_doc = build_index_doc(qa_app, chunks_doc)

    s3.put_object(Bucket="test-bucket", Key="processed/u1/d1/chunks.json", Body=json.dumps(chunks_doc).encode())
    s3.put_object(Bucket="test-bucket", Key="processed/u1/d1/index.json", Body=json.dumps(index_doc).encode())

    monkeypatch.setattr(qa_app, "generate", lambda instruction, text, max_tokens=200: "Mock answer.")

    result = qa_app.lambda_handler(
        {"userId": "u1", "documentId": "d1", "question": "What is the Calvin cycle?"}, None
    )

    assert result["answer"] == "Mock answer."
    assert result["question"] == "What is the Calvin cycle?"
    assert "sourceChunks" in result
