# Latency and performance (M3)

Method: `API_URL=<ApiUrl export> ID_TOKEN=<cognito id token> python3 infra/perf/latency_test.py`
Token: aws cognito-idp admin-initiate-auth (ADMIN_USER_PASSWORD_AUTH) for user1@lecdoc.test, exported as ID_TOKEN. For /ask also export DOC_ID of a processed document.

## API latency (fill from the script output, date and stage: ____)
| test | calls | p50 ms | p95 ms | max ms | errors |
|---|---|---|---|---|---|
| GET /documents sequential | 50 | 919 | 1127 | 1183 | 0 |
| GET /documents 5 x 10 parallel | 50 | 949 | 1122 | 2090 | 0 |
| POST /ask (includes model call) | 5 | 1376 | 1459 | 1459 | 0 |

Client-side numbers include the network round trip from India to us-east-1 and a fresh TLS handshake per call. Server-side numbers from CloudWatch (API Gateway, same 40-minute window, all routes): Latency p50 66 ms, p95 450 ms; IntegrationLatency (Lambda) p50 21 ms, p95 449 ms. The /ask calls ran against a 2-page PDF (2 chunks) and include one Gemma 3 4B call. Measured in the dev account because the demo account has no UI stack; same code and stage-independent configuration.

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
| 5-minute lecture | | | | | |
| 20-page PDF | n/a | | | | |
Prices checked on (date): ____ from the Bedrock and Polly pricing pages.
