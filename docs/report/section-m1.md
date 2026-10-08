# Section M1 - Backend and processing pipeline

Owner: M1. Stack `lecdoc-{stage}-pipeline`. Code in `pipeline/`.

## 1. Pipeline overview

```
Browser --PUT (presigned URL)--> S3 uploads/{userId}/{documentId}/{file}
   S3 "Object Created" --> EventBridge rule (prefix uploads/) --> Step Functions lecdoc-{stage}-pipeline

ParseEvent --> ShouldSkip? --yes--> Done
                  |no
              ChooseType
     audio /            \ pdf
 SplitAudio            ExtractPdf (pypdf)
     |                      |
 TranscribeWindows (Map,    |
   2 windows at a time,     |
   speech model on Bedrock) |
     |                      |
 AssembleAudioText          |
     \_____________________/
              |
 StepChunking -> Chunk -> StepSummarizing -> Summarize -> StepIndexing -> Index -> MarkDone -> Done
 (any failure) ------------------------------------------------------------> MarkFailed -> FailState
```

Each step writes its result to S3 under `processed/{userId}/{documentId}/`. Only the keys and small
values travel in the state, which stays far below the 256 KB Step Functions payload limit.

## 2. Why Step Functions instead of chained Lambdas

- **Visible state.** Every run shows as a graph in the console, with the input and output of every step.
  When something breaks we can see where and why without searching logs.
- **Retries and error handling are declared, not coded.** Each task has the same Retry and Catch blocks
  (section 4). Chained Lambdas would need retry logic and failure bookkeeping in every function.
- **No idle waiting.** A Lambda that waits on another Lambda pays for both. Step Functions waits for free,
  and the Standard workflow allows runs of up to one year (we set a 1-hour timeout).
- **Fan-out with a limit.** The Map state runs the speech calls in parallel with a concurrency cap.
  Building that by hand would need a queue.
- **Cost.** Free-tier state transitions are limited, so the design keeps transitions low: one Task per
  step, and the Map adds about 1 transition per 30 seconds of audio.

## 3. Why 30-second windows and a Map state

- The speech model takes a bounded request. A 5-minute 16 kHz mono WAV is about 9.6 MB. A 30-second
  window is about 960 KB, which is a safe request size and finishes well inside the 60 s Lambda timeout.
- `split-audio` uses Python's built-in `wave` and `audioop` modules (Python 3.12) to downmix stereo to mono
  and resample to 16 kHz. This avoids an ffmpeg layer.
- The Map state transcribes windows in parallel with `MaxConcurrency: 2`. This roughly halves the time
  for long files without flooding the model endpoint, whose throttling would trigger retries anyway.
- Results come back in window order and keep `startSec`/`endSec`, so every transcript segment has a
  timestamp. Those timestamps become the citations (`12:30-13:10`) in Q&A.
- **Known limit:** windows are cut at fixed 30-second marks, so a word at a boundary can be split or
  dropped. A trailing window shorter than 1 second is ignored.

## 4. Retries and failure handling

| Error | Raised when | Handling |
| --- | --- | --- |
| `ThrottlingException` | Model endpoint returns 429 or 5xx, network error or timeout | Retry 4 times, 5 s first wait, backoff x2 (5, 10, 20, 40 s) |
| `Lambda.ServiceException`, `Lambda.AWSLambdaException`, `Lambda.SdkClientException`, `Lambda.TooManyRequestsException` | Lambda service problems | Retry 3 times, 3 s first wait, backoff x2 |
| Plain `Exception` | Permanent problem: bad file, too long, scanned PDF, rejected key | No retry. Catch sends the run to `MarkFailed` |

- Every Task except `ParseEvent` and `MarkFailed` has `Catch: States.ALL -> MarkFailed`. For the Map, the
  Catch sits on the Map state and the Retry on the inner task. `ParseEvent` marks its own failures.
  `MarkDone` also has the Catch, so a failure while saving the result cannot leave an item in PROCESSING.
- `MarkFailed` passes the raw error `Cause` to `update-status`. For a Lambda error this is a JSON string.
  `update-status` keeps only its `errorMessage` field and truncates it to 300 characters. The user sees
  "Audio longer than 5 minutes", not a stack trace.
- User-visible failure messages:

| Case | errorMessage |
| --- | --- |
| Extension other than wav or pdf | Unsupported file type. Use WAV audio or PDF |
| File over 100 MB | File larger than 100 MB |
| Not a 16-bit PCM WAV (mp3 renamed, float or 24-bit WAV, 0-byte file) | Unsupported WAV file / format (need 16-bit PCM ...) with the ffmpeg command |
| Audio longer than 5 minutes | Audio longer than 5 minutes |
| Only silence or noise | No speech detected in audio |
| Text file renamed .pdf, broken PDF | Could not read PDF |
| Password-protected PDF | PDF is encrypted |
| More than 20 pages | PDF has more than 20 pages |
| Scanned PDF (images only) | No text found. PDF may be scanned images |
| Bedrock key expired or wrong | Bedrock API key rejected. Check the key in SSM |

## 5. Duplicate-event protection

EventBridge delivers at least once, so the same upload can start two executions. `parse-event` moves the
item from UPLOADING to PROCESSING with a conditional update (`status = UPLOADING`). The second delivery
fails the condition and returns `{"skip": true}`, so that execution ends at once as Succeeded and does no
work. The same check skips files that were put into `uploads/` without going through `POST /uploads`,
because they have no item.

## 6. Status tracking (single writer)

Only M1 Lambdas write status fields in DynamoDB (`parse-event`, `update-status`). M2's AI Lambdas never
touch the table. Status flow: `UPLOADING -> PROCESSING (step TRANSCRIBING | EXTRACTING -> CHUNKING ->
SUMMARIZING -> INDEXING) -> DONE | FAILED`. On DONE, `update-status` stores the summary, chunkCount and
`processingMs` (DONE time minus `startedAt`), and removes `step`.
`update-status` uses `attribute_exists(userId)`, so a document deleted during processing is never
recreated.

## 7. Document CRUD and data isolation

| Route | Lambda | Behaviour |
| --- | --- | --- |
| POST /uploads | create-upload | Checks extension (wav/pdf) and contentType, sanitizes the file name, writes item UPLOADING, returns a 15-minute presigned PUT URL that has Content-Type signed in |
| GET /documents | list-documents | Query on the partition key `userId`, newest first |
| GET /documents/{id} | get-document | GetItem on (userId, documentId). When DONE, adds a 15-minute presigned GET for text.json |
| DELETE /documents/{id} | delete-document | GetItem (404 if missing), deletes every object under `uploads/{userId}/{documentId}/` and `processed/{userId}/{documentId}/` (audio windows, text, chunks, index, summary, mp3), then the item |

- `userId` always comes from the verified JWT claim `sub`. It is never read from the body, query or path.
- Every DynamoDB access uses `userId` as the partition key, so another user's documentId returns 404.
- Delete removes S3 data first and the item last. If S3 deletion fails, the item stays and the user can
  retry. If a document is deleted while its run is still going, `update-status` fails and the run stops;
  any file written after that is removed by the 60-day lifecycle rule on the data bucket.

## 8. IAM (least privilege, one role per Lambda)

| Lambda | Actions | Resources |
| --- | --- | --- |
| create-upload | dynamodb:PutItem; s3:PutObject | documents table; `data-bucket/uploads/*` |
| list-documents | dynamodb:Query | documents table |
| get-document | dynamodb:GetItem; s3:GetObject | documents table; `data-bucket/processed/*` |
| delete-document | dynamodb:GetItem, DeleteItem; s3:DeleteObject; s3:ListBucket | table; `uploads/*`, `processed/*`; bucket with `s3:prefix` limited to `uploads/*`, `processed/*` |
| parse-event | dynamodb:UpdateItem | documents table |
| split-audio | s3:GetObject; s3:PutObject | `uploads/*`; `processed/*` |
| transcribe-window | s3:GetObject; ssm:GetParameter | `processed/*`; `parameter/lecdoc/{stage}/bedrock-api-key` |
| assemble-audio-text | s3:PutObject | `processed/*` |
| extract-pdf | s3:GetObject; s3:PutObject | `uploads/*`; `processed/*` |
| update-status | dynamodb:GetItem, UpdateItem | documents table |
| state machine role | lambda:InvokeFunction | the 6 pipeline Lambdas + imported chunk, summarize, index |

No `*` actions and no `*` resources. The state machine role has no S3, DynamoDB or model permissions.
The Bedrock API key is read from SSM SecureString at run time and cached per container. It is never in an
environment variable, the template or Git.

## 9. Limits

- Audio: WAV only, 16-bit PCM, mono or stereo, any sample rate, up to 5 minutes. Other formats must be
  converted: `ffmpeg -i in.mp3 -ac 1 -ar 16000 -c:a pcm_s16le out.wav`.
- PDF: text PDFs only, up to 20 pages, not encrypted. Scanned PDFs fail with a clear message.
- Upload size: 50 MB in the frontend, 100 MB hard limit in parse-event.
- Window cuts at fixed 30 s can split words.
- The speech prompt says the audio is English. Without that, the model answered an English sample in
  German, so other languages are not supported.

## 10. Performance

Measured in the dev account, one run per file (see `docs/perf/pipeline-timings.csv`):

| File | Length | Processing time (s) |
| --- | --- | --- |
| audio | 1 min | 7.2 |
| audio | 3 min | 6.9 |
| audio | 5 min (4.9) | 10.8 |
| pdf | 2 pages | 4.8 |
| pdf | 10 pages | 3.0 |
| pdf | 20 pages | 3.5 |

Processing time is `processingMs` (DONE time minus `startedAt`), so it covers the whole state machine:
text extraction or transcription, chunk, summarize (Gemma call) and index. It does not include the
browser upload.

- Audio time grows slowly with length because the Map state transcribes two 30 s windows at a time:
  the 5-minute file has 10 windows but finishes in about 11 s. The 1-minute run was slower than the
  3-minute one because it was the first run after a deploy (Lambda cold starts).
- PDF time hardly depends on page count. pypdf reads 20 pages in well under a second, so most of the
  time is the summary call and the Step Functions transitions.
- Every file finishes far below the 3600 s state machine timeout and the 15-minute Lambda limit.

## 11. Testing

- Unit tests (`pytest pipeline/`): moto mocks S3 and DynamoDB, and the speech call is mocked. Covered:
  bad extension (400), another user's document (404), delete removes both prefixes and the item but not
  neighbours, duplicate event skipped, error Cause parsing, WAV splitting (stereo 44.1 kHz 65 s gives
  3 mono 16 kHz windows; a 301 s file and junk bytes are rejected), PDF extraction (empty, encrypted,
  over 20 pages, not a PDF), HTTP error mapping to ThrottlingException, and the state machine wiring.
- End-to-end runs in the dev account with all six sample files: every one reached DONE with a summary.
- Manual failure runs in the dev account, each ending FAILED with a readable message:
  0-byte .wav ("Unsupported WAV file (need 16-bit PCM). Convert with: ffmpeg ..."), a text file
  renamed .pdf ("Could not read PDF"), a 6-minute WAV ("Audio longer than 5 minutes") and the scanned
  sample PDF ("No text found. PDF may be scanned images").
- Isolation and CRUD in the dev account: user B lists 0 documents and gets 404 on get and delete of
  user A's document; delete by the owner returns 200 and leaves 0 objects under `uploads/` and
  `processed/`; create-upload with `.mp3` returns 400.
