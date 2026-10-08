#!/usr/bin/env python3
"""Cost per document. Fill prices from the AWS pricing pages (they change), then run:
python3 infra/perf/cost.py --stt-per-min P --in-per-1m P --out-per-1m P --audio-min 5 --in-tokens N --out-tokens N [--polly-per-1m-chars P --polly-chars 1500] [--infra 0.0002]"""
import argparse

a = argparse.ArgumentParser()
a.add_argument("--stt-per-min", type=float, default=0.0)
a.add_argument("--in-per-1m", type=float, required=True)
a.add_argument("--out-per-1m", type=float, required=True)
a.add_argument("--audio-min", type=float, default=0.0)
a.add_argument("--in-tokens", type=int, required=True)
a.add_argument("--out-tokens", type=int, required=True)
a.add_argument("--polly-per-1m-chars", type=float, default=0.0)
a.add_argument("--polly-chars", type=int, default=0)
a.add_argument("--infra", type=float, default=0.0002, help="Lambda + Step Functions + S3 estimate per document, USD")
x = a.parse_args()
stt = x.audio_min * x.stt_per_min
llm = x.in_tokens / 1e6 * x.in_per_1m + x.out_tokens / 1e6 * x.out_per_1m
polly = x.polly_chars / 1e6 * x.polly_per_1m_chars
print(f"speech {stt:.4f} + text model {llm:.4f} + polly {polly:.4f} + infra {x.infra:.4f} = USD {stt + llm + polly + x.infra:.4f}")
