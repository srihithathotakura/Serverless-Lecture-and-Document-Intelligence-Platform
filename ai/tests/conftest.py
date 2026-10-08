import importlib.util
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # ai/


@pytest.fixture(autouse=True)
def aws_credentials(monkeypatch):
    """Moto requires dummy credentials present even when mocking AWS calls."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


def load_app(name, rel_path):
    """Load ai/src/<x>/app.py as a uniquely-named module, re-reading env vars fresh."""
    path = os.path.join(ROOT, rel_path)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def chunk_app(monkeypatch):
    monkeypatch.setenv("DATA_BUCKET", "test-bucket")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    return load_app("chunk_app", "src/chunk/app.py")


@pytest.fixture
def index_app(monkeypatch):
    monkeypatch.setenv("DATA_BUCKET", "test-bucket")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    return load_app("index_app", "src/index/app.py")


@pytest.fixture
def summarize_app(monkeypatch):
    monkeypatch.setenv("DATA_BUCKET", "test-bucket")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("BEDROCK_SSM_PARAM", "/lecdoc/test/bedrock-api-key")
    monkeypatch.setenv("TEXT_MODEL_ID", "google.gemma-3-4b-it")
    return load_app("summarize_app", "src/summarize/app.py")


@pytest.fixture
def qa_app(monkeypatch):
    monkeypatch.setenv("DATA_BUCKET", "test-bucket")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("BEDROCK_SSM_PARAM", "/lecdoc/test/bedrock-api-key")
    monkeypatch.setenv("TEXT_MODEL_ID", "google.gemma-3-4b-it")
    return load_app("qa_app", "src/qa/app.py")


@pytest.fixture
def speak_app(monkeypatch):
    monkeypatch.setenv("DATA_BUCKET", "test-bucket")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    return load_app("speak_app", "src/speak/app.py")
