#!/usr/bin/env bash
set -euo pipefail
aws polly synthesize-speech --output-format mp3 --voice-id Joanna \
  --text "Hello from the lecture platform" /tmp/hello.mp3
ls -l /tmp/hello.mp3
