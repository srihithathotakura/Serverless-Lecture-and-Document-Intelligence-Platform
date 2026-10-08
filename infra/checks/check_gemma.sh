#!/usr/bin/env bash
set -euo pipefail
: "${BEDROCK_API_KEY:?export BEDROCK_API_KEY first}"
curl -sf https://bedrock-mantle.us-east-1.api.aws/v1/chat/completions \
  -H "Authorization: Bearer $BEDROCK_API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"google.gemma-3-4b-it","max_tokens":30,"messages":[{"role":"user","content":"say hi"}]}'
echo
