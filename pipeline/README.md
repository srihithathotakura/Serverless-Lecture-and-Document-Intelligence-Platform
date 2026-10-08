# pipeline (M1)

Stack `lecdoc-{stage}-pipeline`: 4 CRUD Lambdas behind the API, 6 pipeline Lambdas, the
`lecdoc-{stage}-pipeline` state machine and the EventBridge rule that starts it on upload.
Contracts: Doc 0 section 9. Design: Doc 1 section 5.

```
src/<lambda_name>/app.py     one folder per Lambda, handler app.lambda_handler
statemachine.asl.json        Step Functions definition (${...} filled by DefinitionSubstitutions)
template.yaml                SAM template, one role per Lambda
events/                      sample payloads for aws lambda invoke
scripts/pipeline_timings.py  writes docs/perf/pipeline-timings.csv from DONE items
tests/                       pytest, moto mocks, no real AWS or model calls
```

## Checks before every merge

```bash
pytest pipeline/
ruff check pipeline/
sam validate --lint -t pipeline/template.yaml
```

## Deploy (own dev account only)

Needs `core` (M3) and `ai` (M2, exports ChunkFnArn, SummarizeFnArn, IndexFnArn) deployed first.
The AI stubs must return the contract shape (`{chunksKey, chunkCount}`, `{summary}`, `{indexKey, chunkCount}`),
otherwise the ResultSelector fails with States.Runtime, which no Catch can handle.

```bash
aws sts get-caller-identity                 # must be YOUR account, never demo
./infra/deploy.sh dev pipeline
aws cloudformation list-exports --query "Exports[?starts_with(Name,'lecdoc-dev')].Name"
```

## Manual test

```bash
# 1. create an upload for user-A (expect statusCode 200 and uploadUrl)
aws lambda invoke --function-name lecdoc-dev-create-upload \
  --cli-binary-format raw-in-base64-out --payload file://pipeline/events/create-upload.json out.json
cat out.json

# 2. PUT the file with the same Content-Type that was signed
curl -X PUT -H "Content-Type: audio/wav" --data-binary @samples/audio-1min.wav "<uploadUrl>"

# 3. watch Step Functions > lecdoc-dev-pipeline > Executions, then list / get / delete
aws lambda invoke --function-name lecdoc-dev-list-documents \
  --cli-binary-format raw-in-base64-out --payload file://pipeline/events/list-documents.json out.json
```

Put the documentId into `events/get-document*.json` / `delete-document.json` before invoking them.
`*-user-b.json` must return an empty list and 404 (isolation check).
For a PDF use `events/create-upload-pdf.json` and `-H "Content-Type: application/pdf"`.

## Speech request format

`stt_transcribe()` in `src/transcribe_window/app.py` is the only place that knows the speech call.
It copies the request from `infra/checks/check_stt.sh`: `POST /chat/completions` with the window as
base64 `input_audio` (format `wav`) plus a transcribe instruction, `max_tokens` 400, reading the transcript
from `choices[0].message.content`. The instruction names the language ("English audio ... Do not
translate"): without it the model answered the English sample in German. If the check script changes,
change only that function.
