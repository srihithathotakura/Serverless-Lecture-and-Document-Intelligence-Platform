import io
import json

import pypdf
import pytest
from m1_helpers import BUCKET, load, make_pdf


def segments(data):
    return load("extract_pdf").extract_segments(io.BytesIO(data))


def test_extract_two_pages():
    assert segments(make_pdf(["Hello   page one", "Page two text"])) == [
        {"text": "Hello page one", "page": 1}, {"text": "Page two text", "page": 2}]


def test_extract_skips_empty_page():
    assert segments(make_pdf(["First", "", "Third"])) == [{"text": "First", "page": 1}, {"text": "Third", "page": 3}]


def test_scanned_pdf_has_no_text():
    with pytest.raises(Exception, match="No text found. PDF may be scanned images"):
        segments(make_pdf(["", ""]))


def test_too_many_pages():
    with pytest.raises(Exception, match="more than 20 pages"):
        segments(make_pdf([f"page {i}" for i in range(21)]))


@pytest.mark.parametrize("data", [b"this is a text file renamed .pdf", b""])
def test_not_a_pdf(data):
    with pytest.raises(Exception, match="Could not read PDF"):
        segments(data)


def test_encrypted_pdf():
    writer = pypdf.PdfWriter(clone_from=pypdf.PdfReader(io.BytesIO(make_pdf(["secret"]))))
    writer.encrypt("pw", algorithm="RC4-40")
    buf = io.BytesIO()
    writer.write(buf)
    with pytest.raises(Exception, match="PDF is encrypted"):
        segments(buf.getvalue())


def test_extract_pdf_handler(aws, tmp_path):
    s3, _ = aws
    s3.put_object(Bucket=BUCKET, Key="uploads/user-A/d1/notes.pdf", Body=make_pdf(["Page one", "Page two"]))
    fn = load("extract_pdf")
    fn.TMP_PATH = str(tmp_path / "in.pdf")

    out = fn.lambda_handler({"userId": "user-A", "documentId": "d1", "bucket": BUCKET,
                             "s3Key": "uploads/user-A/d1/notes.pdf"}, None)
    assert out == {"textKey": "processed/user-A/d1/text.json", "segmentCount": 2}
    doc = json.loads(s3.get_object(Bucket=BUCKET, Key=out["textKey"])["Body"].read())
    assert doc == {"documentId": "d1", "sourceType": "pdf",
                   "segments": [{"text": "Page one", "page": 1}, {"text": "Page two", "page": 2}]}
