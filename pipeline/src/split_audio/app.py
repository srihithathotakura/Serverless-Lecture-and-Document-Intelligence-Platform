import audioop  # removed in Python 3.13, so the runtime stays python3.12
import io
import os
import wave

import boto3

BUCKET = os.environ["DATA_BUCKET"]
s3 = boto3.client("s3")

WIN_SEC, MAX_SEC = 30, 300
TMP_PATH = "/tmp/in.wav"
CONVERT_HINT = "Convert with: ffmpeg -i in.mp3 -ac 1 -ar 16000 -c:a pcm_s16le out.wav"


def split_wav(path_or_file):
    """Return a list of {startSec, endSec, bytes}: 30 s mono 16 kHz 16-bit windows."""
    try:
        w = wave.open(path_or_file, "rb")  # noqa: SIM115 - closed by the with block below
    except (wave.Error, EOFError):
        raise Exception(f"Unsupported WAV file (need 16-bit PCM). {CONVERT_HINT}")
    with w:
        ch, width, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        if width != 2 or ch > 2 or rate <= 0:
            raise Exception(f"Unsupported WAV format (need 16-bit PCM, mono or stereo). {CONVERT_HINT}")
        dur = n / rate
        if dur > MAX_SEC:
            raise Exception("Audio longer than 5 minutes")
        out, state, i = [], None, 0
        while True:
            data = w.readframes(rate * WIN_SEC)
            if not data:
                break
            if ch == 2:
                data = audioop.tomono(data, 2, 0.5, 0.5)
            if rate != 16000:
                data, state = audioop.ratecv(data, 2, 1, rate, 16000, state)
            start, end = i * WIN_SEC, min((i + 1) * WIN_SEC, dur)
            i += 1
            if end - start < 1:          # ignore a trailing window shorter than 1 s
                continue
            buf = io.BytesIO()
            with wave.open(buf, "wb") as o:
                o.setnchannels(1)
                o.setsampwidth(2)
                o.setframerate(16000)
                o.writeframes(data)
            out.append({"startSec": float(start), "endSec": round(end, 1), "bytes": buf.getvalue()})
        if not out:
            raise Exception("Audio is empty or shorter than 1 second")
        return out


def lambda_handler(event, context):
    user_id, document_id = event["userId"], event["documentId"]
    bucket = event.get("bucket") or BUCKET
    s3.download_file(bucket, event["s3Key"], TMP_PATH)

    try:
        parts = split_wav(TMP_PATH)
    finally:
        os.remove(TMP_PATH)

    windows = []
    for n, win in enumerate(parts, start=1):
        key = f"processed/{user_id}/{document_id}/audio/w{n:04d}.wav"
        s3.put_object(Bucket=bucket, Key=key, Body=win["bytes"], ContentType="audio/wav")
        windows.append({"key": key, "startSec": win["startSec"], "endSec": win["endSec"]})
    return {"windows": windows, "windowCount": len(windows)}
