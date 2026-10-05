import io
import json
import urllib.error
import wave
from unittest import mock

import pytest
from m1_helpers import BUCKET, load, make_wav

# ---------- split-audio ----------

def test_split_wav_stereo_44k_65s():
    windows = load("split_audio").split_wav(io.BytesIO(make_wav(65, rate=44100, channels=2)))
    assert [(w["startSec"], w["endSec"]) for w in windows] == [(0.0, 30.0), (30.0, 60.0), (60.0, 65.0)]
    for w in windows:
        with wave.open(io.BytesIO(w["bytes"])) as out:
            assert (out.getnchannels(), out.getsampwidth(), out.getframerate()) == (1, 2, 16000)
            assert abs(out.getnframes() / 16000 - (w["endSec"] - w["startSec"])) < 0.05


def test_split_wav_drops_short_tail():
    windows = load("split_audio").split_wav(io.BytesIO(make_wav(30.5)))
    assert [(w["startSec"], w["endSec"]) for w in windows] == [(0.0, 30.0)]


def test_split_wav_too_long():
    with pytest.raises(Exception, match="longer than 5 minutes"):
        load("split_audio").split_wav(io.BytesIO(make_wav(301, rate=8000)))


@pytest.mark.parametrize("data", [b"junk", b""])
def test_split_wav_not_a_wav(data):
    with pytest.raises(Exception, match="Unsupported WAV file"):
        load("split_audio").split_wav(io.BytesIO(data))


def test_split_wav_8bit_rejected():
    with pytest.raises(Exception, match="Unsupported WAV format"):
        load("split_audio").split_wav(io.BytesIO(make_wav(2, width=1)))


def test_split_wav_empty_audio():
    with pytest.raises(Exception, match="empty"):
        load("split_audio").split_wav(io.BytesIO(make_wav(0)))


def test_split_audio_handler_writes_windows(aws, tmp_path):
    s3, _ = aws
    s3.put_object(Bucket=BUCKET, Key="uploads/user-A/d1/a.wav", Body=make_wav(45))
    fn = load("split_audio")
    fn.TMP_PATH = str(tmp_path / "in.wav")

    out = fn.lambda_handler({"userId": "user-A", "documentId": "d1", "bucket": BUCKET,
                             "s3Key": "uploads/user-A/d1/a.wav"}, None)
    assert out == {"windowCount": 2, "windows": [
        {"key": "processed/user-A/d1/audio/w0001.wav", "startSec": 0.0, "endSec": 30.0},
        {"key": "processed/user-A/d1/audio/w0002.wav", "startSec": 30.0, "endSec": 45.0}]}
    assert not (tmp_path / "in.wav").exists()
    head = s3.head_object(Bucket=BUCKET, Key="processed/user-A/d1/audio/w0002.wav")
    assert head["ContentType"] == "audio/wav"


# ---------- transcribe-window ----------

WINDOW_EVENT = {"userId": "user-A", "documentId": "d1", "bucket": BUCKET,
                "window": {"key": "processed/user-A/d1/audio/w0002.wav", "startSec": 30.0, "endSec": 60.0}}


def test_transcribe_window_handler(aws, capsys):
    s3, _ = aws
    s3.put_object(Bucket=BUCKET, Key="processed/user-A/d1/audio/w0002.wav", Body=b"RIFF...")
    fn = load("transcribe_window")
    with mock.patch.object(fn, "stt_transcribe", return_value="  Hello (...) world\n again ") as stt:
        out = fn.lambda_handler(WINDOW_EVENT, None)
    stt.assert_called_once_with(b"RIFF...")
    assert out == {"startSec": 30.0, "endSec": 60.0, "text": "Hello world again"}
    assert json.loads(capsys.readouterr().out.strip()) == {"event": "STT_USAGE", "seconds": 30.0}


def test_transcribe_window_silence_is_not_an_error(aws):
    s3, _ = aws
    s3.put_object(Bucket=BUCKET, Key="processed/user-A/d1/audio/w0002.wav", Body=b"RIFF...")
    fn = load("transcribe_window")
    with mock.patch.object(fn, "stt_transcribe", return_value=""):
        assert fn.lambda_handler(WINDOW_EVENT, None)["text"] == ""


def test_transcribe_window_rejects_foreign_key():
    fn = load("transcribe_window")
    event = {**WINDOW_EVENT, "window": {**WINDOW_EVENT["window"], "key": "processed/user-B/d9/audio/w0001.wav"}}
    with pytest.raises(Exception, match="does not belong"):
        fn.lambda_handler(event, None)


def test_stt_transcribe_sends_multipart():
    fn = load("transcribe_window")
    fn._key = "test-key"
    seen = {}

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout):
        seen.update(url=req.full_url, headers=dict(req.header_items()), data=req.data)
        return Resp(b'{"text": "hi there"}')

    with mock.patch.object(fn.urllib.request, "urlopen", fake_urlopen):
        assert fn.stt_transcribe(b"WAVDATA") == "hi there"
    assert seen["url"] == "https://mantle.example/v1/audio/transcriptions"
    assert seen["headers"]["Authorization"] == "Bearer test-key"
    assert seen["headers"]["Content-type"].startswith("multipart/form-data; boundary=")
    assert b'name="model"\r\n\r\ntest-stt-model' in seen["data"]
    assert b"WAVDATA" in seen["data"]


@pytest.mark.parametrize("code,exc_name", [(429, "ThrottlingException"), (503, "ThrottlingException"),
                                           (401, "Exception"), (400, "Exception")])
def test_call_model_error_mapping(code, exc_name):
    fn = load("transcribe_window")
    fn._key = "test-key"
    err = urllib.error.HTTPError("u", code, "x", {}, None)
    with mock.patch.object(fn.urllib.request, "urlopen", side_effect=err), pytest.raises(Exception) as info:
        fn.call_model("/x", {"a": 1})
    assert type(info.value).__name__ == exc_name


def test_call_model_timeout_is_retryable():
    fn = load("transcribe_window")
    fn._key = "test-key"
    with mock.patch.object(fn.urllib.request, "urlopen", side_effect=TimeoutError()), \
            pytest.raises(fn.ThrottlingException):
        fn.call_model("/x", {"a": 1})


# ---------- assemble-audio-text ----------

def test_assemble_sorts_cleans_and_drops(aws):
    s3, _ = aws
    windows = [{"startSec": 30.0, "endSec": 60.0, "text": "second   window (...) here"},
               {"startSec": 0.0, "endSec": 30.0, "text": "first window"},
               {"startSec": 60.0, "endSec": 65.0, "text": "uh"},
               {"startSec": 90.0, "endSec": 120.0, "text": ""}]
    out = load("assemble_audio_text").lambda_handler(
        {"userId": "user-A", "documentId": "d1", "bucket": BUCKET, "windows": windows}, None)
    assert out == {"textKey": "processed/user-A/d1/text.json", "segmentCount": 2}
    doc = json.loads(s3.get_object(Bucket=BUCKET, Key=out["textKey"])["Body"].read())
    assert doc == {"documentId": "d1", "sourceType": "audio", "segments": [
        {"text": "first window", "startSec": 0.0, "endSec": 30.0},
        {"text": "second window here", "startSec": 30.0, "endSec": 60.0}]}


def test_assemble_no_speech(aws):
    with pytest.raises(Exception, match="No speech detected in audio"):
        load("assemble_audio_text").lambda_handler(
            {"userId": "user-A", "documentId": "d1", "bucket": BUCKET,
             "windows": [{"startSec": 0.0, "endSec": 30.0, "text": "(...)"}]}, None)
