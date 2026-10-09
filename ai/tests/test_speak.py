import boto3
from moto import mock_aws


class FakeStream:
    def __init__(self, data):
        self.data = data

    def read(self):
        return self.data


class FakePolly:
    def __init__(self):
        self.calls = []

    def synthesize_speech(self, Text, OutputFormat, VoiceId):
        self.calls.append({"Text": Text, "OutputFormat": OutputFormat, "VoiceId": VoiceId})
        return {"AudioStream": FakeStream(b"fake-audio-bytes")}


def test_synthesize_speech_calls_polly_with_text_and_voice(speak_app):
    fake_polly = FakePolly()
    speak_app.polly = fake_polly

    audio_bytes = speak_app.synthesize_speech("Hello world", voice_id="Joanna")

    assert audio_bytes == b"fake-audio-bytes"
    assert fake_polly.calls[0]["Text"] == "Hello world"
    assert fake_polly.calls[0]["OutputFormat"] == "mp3"
    assert fake_polly.calls[0]["VoiceId"] == "Joanna"


@mock_aws
def test_lambda_handler_reads_summary_writes_audio_returns_url(speak_app):
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-bucket")
    s3.put_object(
        Bucket="test-bucket",
        Key="processed/u1/d1/summary.txt",
        Body=b"This is the summary text.",
        ContentType="text/plain",
    )

    speak_app.polly = FakePolly()

    result = speak_app.lambda_handler({"userId": "u1", "documentId": "d1"}, None)

    assert "audioUrl" in result
    assert result["expiresIn"] == 900
    assert "summary.mp3" in result["audioUrl"]

    obj = s3.get_object(Bucket="test-bucket", Key="processed/u1/d1/summary.mp3")
    assert obj["Body"].read() == b"fake-audio-bytes"
    assert obj["ContentType"] == "audio/mpeg"


@mock_aws
def test_lambda_handler_returns_error_when_no_summary_exists(speak_app):
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-bucket")

    speak_app.polly = FakePolly()

    result = speak_app.lambda_handler({"userId": "u1", "documentId": "missing-doc"}, None)

    assert "error" in result


def test_lambda_handler_requires_document_id(speak_app):
    result = speak_app.lambda_handler({"userId": "u1"}, None)
    assert "error" in result


def test_parse_request_api_gateway_body(speak_app):
    document_id = speak_app.parse_request({"body": '{"documentId": "d1"}'})
    assert document_id == "d1"
