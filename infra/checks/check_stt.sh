#!/usr/bin/env bash
# usage: ./infra/checks/check_stt.sh <file.wav>
# Sends the first 30 s of a WAV to the speech model and prints the text.
# M1: copy this request shape into stt_transcribe() in transcribe_window.
set -euo pipefail
: "${BEDROCK_API_KEY:?export BEDROCK_API_KEY first}"
WAV=${1:?usage: check_stt.sh file.wav}
MODEL=${STT_MODEL_ID:-mistral.voxtral-mini-3b-2507}
URL=https://bedrock-mantle.us-east-1.api.aws/v1/chat/completions
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT

ffmpeg -loglevel error -y -i "$WAV" -t 30 -ac 1 -ar 16000 -c:a pcm_s16le "$TMP/clip.wav"
base64 -w0 "$TMP/clip.wav" > "$TMP/clip.b64"
jq -n --arg m "$MODEL" --rawfile b "$TMP/clip.b64" '{
  model: $m, max_tokens: 400,
  messages: [{role: "user", content: [
    {type: "input_audio", input_audio: {data: $b, format: "wav"}},
    {type: "text", text: "Transcribe this audio exactly. Output only the transcript."}]}]}' > "$TMP/body.json"

CODE=$(curl -s -o "$TMP/resp.json" -w '%{http_code}' "$URL" \
  -H "Authorization: Bearer $BEDROCK_API_KEY" -H "Content-Type: application/json" -d @"$TMP/body.json")
if [ "$CODE" != 200 ]; then echo "HTTP $CODE"; cat "$TMP/resp.json"; exit 1; fi

TEXT=$(jq -r '.choices[0].message.content // empty' "$TMP/resp.json")
[ -n "$TEXT" ] || { echo "empty transcript"; cat "$TMP/resp.json"; exit 1; }
echo "model: $MODEL"
echo "text:  $TEXT"
