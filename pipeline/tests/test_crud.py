import json
from urllib.parse import parse_qs, urlparse

from m1_helpers import BUCKET, api_event, load


def body_of(result):
    return json.loads(result["body"])


def create(user, file_name="a.wav", content_type="audio/wav"):
    fn = load("create_upload")
    return fn.lambda_handler(api_event(user, json.dumps({"fileName": file_name, "contentType": content_type})), None)


def put_item(table, user, doc, **extra):
    table.put_item(Item={"userId": user, "documentId": doc, "status": "UPLOADING", "fileName": "a.wav",
                         "createdAt": "2026-10-05T10:00:00Z", **extra})


# ---------- create-upload ----------

def test_create_upload_wav(aws):
    _, table = aws
    result = create("user-A", "My Lecture (1).wav")
    assert result["statusCode"] == 200
    body = body_of(result)
    assert len(body["documentId"]) == 32 and "-" not in body["documentId"]
    assert body["s3Key"] == f"uploads/user-A/{body['documentId']}/My_Lecture__1_.wav"
    assert body["expiresIn"] == 900
    url = urlparse(body["uploadUrl"])
    assert BUCKET in url.netloc + url.path
    assert "content-type" in parse_qs(url.query)["X-Amz-SignedHeaders"][0]

    item = table.get_item(Key={"userId": "user-A", "documentId": body["documentId"]})["Item"]
    assert item["status"] == "UPLOADING"
    assert item["fileType"] == "audio"
    assert item["contentType"] == "audio/wav"
    assert item["createdAt"].endswith("Z")


def test_create_upload_pdf_file_type(aws):
    _, table = aws
    body = body_of(create("user-A", "Notes.PDF", "application/pdf"))
    item = table.get_item(Key={"userId": "user-A", "documentId": body["documentId"]})["Item"]
    assert item["fileType"] == "pdf"


def test_create_upload_bad_extension(aws):
    _, table = aws
    result = create("user-A", "a.mp3", "audio/mpeg")
    assert result["statusCode"] == 400
    assert body_of(result) == {"error": "Unsupported file type. Use WAV audio or PDF"}
    assert table.scan()["Count"] == 0


def test_create_upload_bad_content_type(aws):
    assert create("user-A", "a.wav", "")["statusCode"] == 400
    assert create("user-A", "a.wav", "x" * 101)["statusCode"] == 400


def test_create_upload_bad_body(aws):
    fn = load("create_upload")
    assert fn.lambda_handler(api_event("user-A", "not json"), None)["statusCode"] == 400
    assert fn.lambda_handler(api_event("user-A", "[]"), None)["statusCode"] == 400
    assert fn.lambda_handler(api_event("user-A", "{}"), None)["statusCode"] == 400


def test_create_upload_ignores_user_id_in_body(aws):
    fn = load("create_upload")
    body = json.dumps({"fileName": "a.wav", "contentType": "audio/wav", "userId": "user-B"})
    result = body_of(fn.lambda_handler(api_event("user-A", body), None))
    assert result["s3Key"].startswith("uploads/user-A/")


def test_sanitize_keeps_extension():
    fn_name = load("create_upload").sanitize("x" * 300 + ".wav", "wav")
    assert len(fn_name) == 100 and fn_name.endswith(".wav")


# ---------- list-documents ----------

def test_list_newest_first_and_isolated(aws):
    _, table = aws
    put_item(table, "user-A", "d1", createdAt="2026-10-05T10:00:00Z")
    put_item(table, "user-A", "d2", createdAt="2026-10-05T11:00:00Z", chunkCount=3)
    put_item(table, "user-B", "d3")
    fn = load("list_documents")
    docs = body_of(fn.lambda_handler(api_event("user-A"), None))["documents"]
    assert [d["documentId"] for d in docs] == ["d2", "d1"]
    assert docs[0]["chunkCount"] == 3  # Decimal converted
    assert body_of(load("list_documents").lambda_handler(api_event("user-C"), None)) == {"documents": []}


# ---------- get-document ----------

def test_get_document_other_user_404(aws):
    _, table = aws
    put_item(table, "user-A", "d1")
    fn = load("get_document")
    result = fn.lambda_handler(api_event("user-B", document_id="d1"), None)
    assert result["statusCode"] == 404
    assert "error" in body_of(result)


def test_get_document_text_url_only_when_done(aws):
    _, table = aws
    put_item(table, "user-A", "d1", status="PROCESSING")
    put_item(table, "user-A", "d2", status="DONE")
    fn = load("get_document")
    processing = body_of(fn.lambda_handler(api_event("user-A", document_id="d1"), None))
    assert processing["document"]["status"] == "PROCESSING"
    assert "textUrl" not in processing
    done = body_of(fn.lambda_handler(api_event("user-A", document_id="d2"), None))
    assert "processed/user-A/d2/text.json" in done["textUrl"]


# ---------- delete-document ----------

def test_delete_removes_s3_and_item(aws):
    s3, table = aws
    put_item(table, "user-A", "d1")
    keys = ["uploads/user-A/d1/a.wav", "processed/user-A/d1/audio/w0001.wav", "processed/user-A/d1/text.json",
            "processed/user-A/d1/index.json", "processed/user-A/d1/summary.txt",
            "processed/user-A/d10/text.json", "uploads/user-B/d1/a.wav"]  # last two must survive
    for k in keys:
        s3.put_object(Bucket=BUCKET, Key=k, Body=b"x")

    result = load("delete_document").lambda_handler(api_event("user-A", document_id="d1"), None)
    assert result["statusCode"] == 200
    assert body_of(result) == {"deleted": True}
    left = sorted(o["Key"] for o in s3.list_objects_v2(Bucket=BUCKET).get("Contents", []))
    assert left == ["processed/user-A/d10/text.json", "uploads/user-B/d1/a.wav"]
    assert "Item" not in table.get_item(Key={"userId": "user-A", "documentId": "d1"})


def test_delete_other_user_404_keeps_data(aws):
    s3, table = aws
    put_item(table, "user-A", "d1")
    s3.put_object(Bucket=BUCKET, Key="uploads/user-A/d1/a.wav", Body=b"x")
    result = load("delete_document").lambda_handler(api_event("user-B", document_id="d1"), None)
    assert result["statusCode"] == 404
    assert "Item" in table.get_item(Key={"userId": "user-A", "documentId": "d1"})
    assert s3.list_objects_v2(Bucket=BUCKET)["KeyCount"] == 1
