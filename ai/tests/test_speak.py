import boto3
from moto import mock_aws


def test_synthesize_speech_calls_polly_with_text_and_voice(speak_app, monkeypatch):
    captured = {}

    class FakeStream:
        def read(self):
            return b"fake-mp3-bytes"

    class FakePolly:
        def synthesize_speech(self, Text, OutputFormat, VoiceId):
            captured["Text"] = Text
            captured["OutputFormat"] = OutputFormat
            captured["VoiceId"] = VoiceId
            return {"AudioStream": FakeStream()}

    speak_app.polly = FakePolly()

    audio_bytes = speak_app.synthesize_speech("Hello world", voice_id="Joanna")

    assert audio_bytes == b"fake-mp3-bytes"
    assert captured["Text"] == "Hello world"
    assert captured["OutputFormat"] == "mp3"
    assert captured["VoiceId"] == "Joanna"


@mock_aws
def test_lambda_handler_writes_audio_to_s3(speak_app):
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-bucket")

    class FakeStream:
        def read(self):
            return b"fake-audio-data"

    class FakePolly:
        def synthesize_speech(self, Text, OutputFormat, VoiceId):
            return {"AudioStream": FakeStream()}

    speak_app.polly = FakePolly()

    result = speak_app.lambda_handler(
        {"userId": "u1", "documentId": "d1", "text": "Hello world"}, None
    )

    assert result["audioKey"] == "processed/u1/d1/speech-Joanna.mp3"
    assert result["bytes"] == len(b"fake-audio-data")

    obj = s3.get_object(Bucket="test-bucket", Key="processed/u1/d1/speech-Joanna.mp3")
    assert obj["Body"].read() == b"fake-audio-data"
    assert obj["ContentType"] == "audio/mpeg"


@mock_aws
def test_lambda_handler_respects_custom_voice_id(speak_app):
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-bucket")

    class FakeStream:
        def read(self):
            return b"x"

    class FakePolly:
        def synthesize_speech(self, Text, OutputFormat, VoiceId):
            assert VoiceId == "Matthew"
            return {"AudioStream": FakeStream()}

    speak_app.polly = FakePolly()

    result = speak_app.lambda_handler(
        {"userId": "u1", "documentId": "d1", "text": "Hi", "voiceId": "Matthew"}, None
    )

    assert result["audioKey"] == "processed/u1/d1/speech-Matthew.mp3"
