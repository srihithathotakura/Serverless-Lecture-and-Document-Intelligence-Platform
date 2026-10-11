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
