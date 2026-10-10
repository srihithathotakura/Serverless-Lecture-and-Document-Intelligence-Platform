# Latency and performance (M3)

Method: `API_URL=<ApiUrl export> ID_TOKEN=<cognito id token> python3 infra/perf/latency_test.py`
Token: M4's `tests/get_token.py`, or copy the ID token from browser dev tools. Run against the demo account after a warm-up call.

## API latency (fill from the script output, date and stage: ____)
| test | calls | p50 ms | p95 ms | max ms | errors |
|---|---|---|---|---|---|
| GET /documents sequential | 50 | | | | |
| GET /documents 5 x 10 parallel | 50 | | | | |
| POST /ask (includes model call) | 5 | | | | |

## Processing time versus file length (from M1's docs/perf/pipeline-timings.csv)
| file | length | processing seconds |
|---|---|---|
| audio-1min.wav | 1 min | |
| audio-3min.wav | 3 min | |
| audio-5min.wav | 5 min | |
| doc-2pages.pdf | 2 pages | |
| doc-10pages.pdf | 10 pages | |
| doc-20pages.pdf | 20 pages | |

Audio time grows with the number of 30-second windows (2 per minute), transcribed two at a time by the Map state. PDF time is dominated by the summary model call, so it grows slowly with page count.

## Cost per document
Run `python3 infra/perf/cost.py ...` with current prices and M2's token counts.
| document | speech | text model | polly | infra | total USD |
|---|---|---|---|---|---|
| 5-minute lecture | 0.0007 | 0.0001 | 0.0060 | 0.0007 | 0.0074 |
| 20-page PDF | n/a | 0.0002 | 0.0060 | 0.0004 | 0.0065 |
Prices checked on (date): 2026-10-10 from the Bedrock and Polly pricing pages.
Without the optional Polly summary the totals are about 0.0015 USD (5-minute lecture) and 0.0005 USD (20-page PDF). Speech cost is an upper bound because only audio seconds are logged, not model usage tokens. Token counts come from M2 (5-minute lecture: 1023 in, 263 out; 20-page PDF: 3392 in, 271 out).
