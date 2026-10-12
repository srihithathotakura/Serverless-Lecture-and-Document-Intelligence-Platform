import os
import uuid

import boto3
import pytest
import requests

REGION = "us-east-1"
STAGE = os.environ.get("STAGE", "dev")
FAKE_ID = "0" * 32

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_AWS_TESTS") != "1",
    reason="Set RUN_AWS_TESTS=1 to run AWS isolation tests",
)


def get_exports():
    cf = boto3.client("cloudformation", region_name=REGION)
    return {
        item["Name"]: item["Value"]
        for page in cf.get_paginator("list_exports").paginate()
        for item in page["Exports"]
    }


def get_token(email):
    password = os.environ.get("TEST_PASSWORD")
    if not password:
        pytest.fail("Set TEST_PASSWORD in the environment; do not put it in this file.")

    exports = get_exports()
    client = boto3.client("cognito-idp", region_name=REGION)
    response = client.admin_initiate_auth(
        UserPoolId=exports[f"lecdoc-{STAGE}-UserPoolId"],
        ClientId=exports[f"lecdoc-{STAGE}-UserPoolClientId"],
        AuthFlow="ADMIN_USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": email, "PASSWORD": password},
    )
    return response["AuthenticationResult"]["IdToken"]


@pytest.fixture(scope="session")
def api():
    return get_exports()[f"lecdoc-{STAGE}-ApiUrl"].rstrip("/")


@pytest.fixture(scope="session")
def h1():
    return {
        "Authorization": f"Bearer {get_token('user1@lecdoc.test')}",
        "Content-Type": "application/json",
    }


@pytest.fixture(scope="session")
def h2():
    return {
        "Authorization": f"Bearer {get_token('user2@lecdoc.test')}",
        "Content-Type": "application/json",
    }


ROUTES = [
    ("POST", "/uploads"),
    ("GET", "/documents"),
    ("GET", f"/documents/{FAKE_ID}"),
    ("DELETE", f"/documents/{FAKE_ID}"),
    ("POST", "/ask"),
    ("POST", "/speak"),
]


@pytest.fixture(scope="module")
def doc1(api, h1):
    response = requests.post(
        f"{api}/uploads",
        headers=h1,
        json={
            "fileName": f"isolation-{uuid.uuid4().hex[:8]}.pdf",
            "contentType": "application/pdf",
        },
        timeout=30,
    )
    assert response.status_code == 200, (
        f"Could not create test document: HTTP {response.status_code}"
    )
    document_id = response.json()["documentId"]
    yield document_id

    # Best-effort cleanup using the owning user's token.
    requests.delete(
        f"{api}/documents/{document_id}", headers=h1, timeout=30
    )


@pytest.mark.parametrize("method,path", ROUTES)
def test_1_no_token_is_401(api, method, path):
    response = requests.request(
        method, f"{api}{path}", json={}, timeout=30
    )
    assert response.status_code == 401, (
        f"{method} {path}: expected 401, got {response.status_code}"
    )


@pytest.mark.parametrize("method,path", ROUTES)
def test_2_garbage_token_is_401(api, method, path):
    response = requests.request(
        method,
        f"{api}{path}",
        headers={"Authorization": "Bearer not.a.valid.token"},
        json={},
        timeout=30,
    )
    assert response.status_code == 401, (
        f"{method} {path}: expected 401, got {response.status_code}"
    )


def test_3_other_user_cannot_get_document(api, h2, doc1):
    response = requests.get(
        f"{api}/documents/{doc1}", headers=h2, timeout=30
    )
    assert response.status_code == 404, (
        f"Expected 404 for another user's document, got {response.status_code}"
    )


def test_4_other_user_cannot_delete_document(api, h1, h2, doc1):
    response = requests.delete(
        f"{api}/documents/{doc1}", headers=h2, timeout=30
    )
    assert response.status_code == 404, (
        f"Expected 404 when another user deletes the document, "
        f"got {response.status_code}"
    )

    owner_list = requests.get(
        f"{api}/documents", headers=h1, timeout=30
    )
    assert owner_list.status_code == 200
    owner_ids = [
        item["documentId"]
        for item in owner_list.json().get("documents", [])
    ]
    assert doc1 in owner_ids, "Document should remain visible to its owner"


def test_5_other_user_list_excludes_document(api, h2, doc1):
    response = requests.get(
        f"{api}/documents", headers=h2, timeout=30
    )
    assert response.status_code == 200
    other_user_ids = [
        item["documentId"]
        for item in response.json().get("documents", [])
    ]
    assert doc1 not in other_user_ids


def test_6_upload_ignores_forged_user_id(api, h1, h2):
    response = requests.post(
        f"{api}/uploads",
        headers=h1,
        json={
            "fileName": f"iso6-{uuid.uuid4().hex[:8]}.pdf",
            "contentType": "application/pdf",
            "userId": "user2",
        },
        timeout=30,
    )
    assert response.status_code == 200, (
        f"Upload failed: HTTP {response.status_code}"
    )

    result = response.json()
    document_id = result["documentId"]
    s3_key = result["s3Key"]

    try:
        # The key must use the authenticated Cognito subject, not body.userId.
        token = h1["Authorization"].split()[1]
        import base64
        import json

        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        owner_sub = json.loads(base64.urlsafe_b64decode(payload))["sub"]

        assert s3_key.startswith(f"uploads/{owner_sub}/{document_id}/"), (
            f"Upload used an unexpected S3 namespace: {s3_key}"
        )
        assert "/user2/" not in s3_key

        owner_get = requests.get(
            f"{api}/documents/{document_id}", headers=h1, timeout=30
        )
        assert owner_get.status_code == 200, (
            f"Owner could not get document: HTTP {owner_get.status_code}"
        )

        other_get = requests.get(
            f"{api}/documents/{document_id}", headers=h2, timeout=30
        )
        assert other_get.status_code == 404, (
            f"Other user should get 404, got {other_get.status_code}"
        )
    finally:
        requests.delete(
            f"{api}/documents/{document_id}", headers=h1, timeout=30
        )


def get_done_document(api, h1):
    """Return a completed document owned by user 1, or skip content tests."""
    response = requests.get(f"{api}/documents", headers=h1, timeout=30)
    assert response.status_code == 200, (
        f"Could not list owner documents: HTTP {response.status_code}"
    )

    for item in response.json().get("documents", []):
        if item.get("status") != "DONE":
            continue

        document_id = item["documentId"]
        detail = requests.get(
            f"{api}/documents/{document_id}", headers=h1, timeout=30
        )
        if detail.status_code != 200:
            continue

        document = detail.json().get("document", {})
        if document.get("textUrl"):
            return document_id, document

    pytest.skip("No completed owner document with extracted text is available")


def test_7_other_user_ask_cannot_leak_document(api, h1, h2):
    document_id, document = get_done_document(api, h1)

    # Fetch the owner's extracted text only to create a distinctive test marker.
    text_response = requests.get(document["textUrl"], timeout=30)
    assert text_response.status_code == 200, (
        f"Could not fetch owner text: HTTP {text_response.status_code}"
    )
    text_doc = text_response.json()

    segments = text_doc.get("segments", [])
    source_text = " ".join(
        segment.get("text", "")
        for segment in segments
        if isinstance(segment, dict)
    ).strip()
    if not source_text:
        pytest.skip("Completed document has no extracted text segments")

    marker = source_text[:80]
    question_words = " ".join(source_text.split()[:8])
    if not question_words:
        pytest.skip("Could not derive a question from the document text")

    response = requests.post(
        f"{api}/ask",
        headers=h2,
        json={"question": question_words, "documentId": document_id},
        timeout=35,
    )
    payload = response.text
    assert marker not in payload, "Ask response leaked the owner's extracted text"

    try:
        data = response.json()
    except ValueError:
        data = {}

    citations = data.get("citations", [])
    assert all(
        citation.get("documentId") != document_id
        for citation in citations
        if isinstance(citation, dict)
    ), "Ask response cited another user's document"

    # Omitting documentId must not expose the owner's document either.
    missing_id_response = requests.post(
        f"{api}/ask",
        headers=h2,
        json={"question": question_words},
        timeout=35,
    )
    assert marker not in missing_id_response.text, (
        "Ask response without documentId leaked the owner's text"
    )


def test_8_other_user_cannot_speak_document(api, h1, h2):
    document_id, _ = get_done_document(api, h1)

    response = requests.post(
        f"{api}/speak",
        headers=h2,
        json={"documentId": document_id},
        timeout=35,
    )

    # The other user's summary must never be returned as an audio URL.
    try:
        payload = response.json()
    except ValueError:
        payload = {}

    assert "audioUrl" not in payload, (
        "Speak returned an audio URL for another user's document"
    )
    assert response.status_code == 404, (
        f"Expected 404 for another user's document, got {response.status_code}"
    )
