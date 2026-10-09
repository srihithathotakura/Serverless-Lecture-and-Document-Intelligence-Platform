import json

import boto3
from moto import mock_aws


def sample_index_doc():
    return {
        "documentId": "doc1",
        "fileName": "lecture1.wav",
        "sourceType": "audio",
        "method": "tfidf-v1",
        "chunks": [
            {
                "chunkId": "doc1#0001",
                "text": "Welcome to the lecture on plants and light reactions.",
                "startSec": 0.0,
                "endSec": 30.0,
                "pageStart": None,
                "pageEnd": None,
                "tf": {"welcome": 1, "lecture": 1, "plants": 1, "light": 1, "reactions": 1},
            },
            {
                "chunkId": "doc1#0002",
                "text": "The Calvin cycle fixes carbon dioxide into glucose in the stroma.",
                "startSec": 30.0,
                "endSec": 60.0,
                "pageStart": None,
                "pageEnd": None,
                "tf": {"calvin": 1, "cycle": 1, "fixes": 1, "carbon": 1, "dioxide": 1, "glucose": 1, "stroma": 1},
            },
        ],
    }


def sample_pdf_index_doc():
    return {
        "documentId": "doc2",
        "fileName": "notes.pdf",
        "sourceType": "pdf",
        "method": "tfidf-v1",
        "chunks": [
            {
                "chunkId": "doc2#0001",
                "text": "Serverless computing removes server management.",
                "startSec": None,
                "endSec": None,
                "pageStart": 1,
                "pageEnd": 1,
                "tf": {"serverless": 1, "computing": 1, "removes": 1, "server": 1, "management": 1},
            },
        ],
    }


def test_tfidf_search_ranks_relevant_chunk_first(qa_app):
    index_doc = sample_index_doc()
    result = qa_app.tfidf_search(index_doc, "What is the Calvin cycle?")

    assert len(result) >= 1
    assert result[0]["chunkId"] == "doc1#0002"


def test_make_label_audio_chunk(qa_app):
    index_doc = sample_index_doc()
    label = qa_app.make_label(index_doc["chunks"][1])
    assert label == "0:30-1:00"


def test_make_label_pdf_single_page(qa_app):
    index_doc = sample_pdf_index_doc()
    label = qa_app.make_label(index_doc["chunks"][0])
    assert label == "p.1"


def test_answer_question_builds_citations_and_calls_generate(qa_app, monkeypatch):
    index_doc = sample_index_doc()

    captured = {}

    def fake_generate(instruction, text, max_tokens=200):
        captured["instruction"] = instruction
        return "The Calvin cycle fixes carbon dioxide."

    monkeypatch.setattr(qa_app, "generate", fake_generate)

    result = qa_app.answer_question(index_doc, "What is the Calvin cycle?")

    assert result["answer"] == "The Calvin cycle fixes carbon dioxide."
    assert len(result["citations"]) >= 1
    assert result["citations"][0]["documentId"] == "doc1"
    assert result["citations"][0]["fileName"] == "lecture1.wav"
    assert "label" in result["citations"][0]
    assert "snippet" in result["citations"][0]
    assert "Calvin cycle" in captured["instruction"]


@mock_aws
def test_lambda_handler_reads_index_from_s3(qa_app, monkeypatch):
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-bucket")

    index_doc = sample_index_doc()
    s3.put_object(Bucket="test-bucket", Key="processed/u1/d1/index.json", Body=json.dumps(index_doc).encode())

    monkeypatch.setattr(qa_app, "generate", lambda instruction, text, max_tokens=200: "Mock answer.")

    result = qa_app.lambda_handler(
        {"userId": "u1", "documentId": "d1", "question": "What is the Calvin cycle?"}, None
    )

    assert result["answer"] == "Mock answer."
    assert "citations" in result


def test_lambda_handler_requires_question(qa_app):
    result = qa_app.lambda_handler({"userId": "u1", "documentId": "d1"}, None)
    assert "error" in result


def test_lambda_handler_requires_document_id(qa_app):
    result = qa_app.lambda_handler({"userId": "u1", "question": "hi"}, None)
    assert "error" in result


def test_lambda_handler_parses_api_gateway_body(qa_app, monkeypatch):
    monkeypatch.setattr(qa_app, "generate", lambda instruction, text, max_tokens=200: "ok")

    question, document_id = qa_app.parse_request(
        {"body": json.dumps({"question": "hi", "documentId": "d1"})}
    )
    assert question == "hi"
    assert document_id == "d1"
