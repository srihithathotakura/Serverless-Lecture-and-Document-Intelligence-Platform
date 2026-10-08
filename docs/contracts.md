# Contracts (FROZEN)

## Change Log

| Date | Change | Approved by |
|---|---|---|
| 2026-10-08 | Copied Doc 0 §9 Contracts into this file. | Pending M3 review |

## 9.1 Naming

| Thing | Name |
|---|---|
| Stack | `lecdoc-{stage}-{name}` where name is core, auth, ai, pipeline, api, web or monitoring |
| Lambda function | `lecdoc-{stage}-{name}`, names in section 9.9 |
| DynamoDB table | `lecdoc-{stage}-documents` |
| Data bucket | `lecdoc-{stage}-data-{accountId}` |
| Web bucket | `lecdoc-{stage}-web-{accountId}` |
| State machine | `lecdoc-{stage}-pipeline` |
| HTTP API | `lecdoc-{stage}-api` |
| User pool | `lecdoc-{stage}-users` |
| SNS topic | `lecdoc-{stage}-alerts` |
| SSM parameter (Bedrock key) | `/lecdoc/{stage}/bedrock-api-key` (SecureString, created by deploy.sh from `BEDROCK_API_KEY`) |
| Stack tags | `project=lecdoc`, `stage={stage}`, `owner={m1..m4}` (added by deploy script) |

## 9.2 Stacks, owners, deploy order

| Order | Stack and template | Owner | Depends on | Contains |
|---|---|---|---|---|
| 1 | core - `infra/core.yaml` | M3 | none | data bucket, documents table, alert topic |
| 2 | auth - `auth/template.yaml` | M4 | none | Cognito user pool and app client |
| 3 | ai - `ai/template.yaml` (SAM) | M2 | core | Lambdas chunk, summarize, index, qa, speak |
| 4 | pipeline - `pipeline/template.yaml` (SAM) | M1 | core, ai | CRUD Lambdas, pipeline Lambdas, state machine, EventBridge rule |
| 5 | api - `api/template.yaml` | M4 | core, auth, ai, pipeline | HTTP API, JWT authorizer, routes, invoke permissions |
| 6 | web - `frontend/template.yaml` | M4 | none | web bucket, CloudFront |
| 7 | monitoring - `infra/monitoring.yaml` | M3 | core, api | dashboard, alarms |

Delete order is the reverse. Stacks talk only through CloudFormation exports (section 9.3) and fixed names. The Bedrock key parameter is not part of any stack: deploy.sh creates it before the first stack.

## 9.3 CloudFormation exports

Full export name = `lecdoc-{stage}-{Suffix}`. Import with `Fn::ImportValue`. Never rename an export or change what it points to. CloudFormation blocks edits to an export that another stack uses.

| Suffix | Value | Stack |
|---|---|---|
| `DataBucketName / DataBucketArn` | data bucket | core |
| `DocumentsTableName / DocumentsTableArn` | documents table | core |
| `AlertTopicArn` | SNS alert topic | core |
| `UserPoolId / UserPoolArn / UserPoolClientId` | Cognito pool and web client | auth |
| `ChunkFnArn / SummarizeFnArn / IndexFnArn / QaFnArn / SpeakFnArn` | AI Lambda ARNs | ai |
| `CreateUploadFnArn / ListDocumentsFnArn / GetDocumentFnArn / DeleteDocumentFnArn` | CRUD Lambda ARNs | pipeline |
| `StateMachineArn` | Step Functions ARN | pipeline |
| `ApiId / ApiUrl` | HTTP API id and base URL (no trailing slash) | api |
| `WebBucketName / CloudFrontDistributionId / WebUrl` | frontend hosting | web |

## 9.4 S3 key layout (data bucket)

```text
uploads/{userId}/{documentId}/{fileName}
processed/{userId}/{documentId}/audio/w0001.wav
processed/{userId}/{documentId}/text.json
processed/{userId}/{documentId}/chunks.json
processed/{userId}/{documentId}/index.json
processed/{userId}/{documentId}/summary.txt
processed/{userId}/{documentId}/summary.mp3
```
- `userId` = Cognito sub. `documentId` = uuid4 hex (32 chars, no dashes).
- `fileName` is sanitized: characters outside A-Za-z0-9._- become `_`, max 100 chars.
- Allowed audio extension: wav only (16-bit PCM, mono or stereo, up to 5 minutes). PDF: pdf (text PDFs, up to 20 pages).
- Convert other audio first, for example: `ffmpeg -i in.mp3 -ac 1 -ar 16000 -c:a pcm_s16le out.wav`
- Limits: frontend blocks files over 50 MB. parse-event hard-rejects over 100 MB.
- Only keys under `uploads/` trigger the pipeline.

## 9.5 DynamoDB table `documents`

- Partition key `userId` (S). Sort key `documentId` (S). On-demand billing. Encryption on. No GSI.
- Access patterns: list a user's documents (Query by userId), get one (GetItem), create, update status, delete.

| Attribute | Type | Written by | Notes |
|---|---|---|---|
| `userId, documentId` | S | create-upload | keys |
| `fileName, contentType, s3Key` | S | create-upload | original name, MIME type, upload key |
| `fileType` | S | create-upload | audio or pdf (from extension) |
| `status` | S | create-upload, parse-event, update-status | UPLOADING, PROCESSING, DONE, FAILED |
| `step` | S | parse-event, update-status | TRANSCRIBING, EXTRACTING, CHUNKING, SUMMARIZING, INDEXING. Removed when DONE or FAILED |
| `summary` | S | update-status | set on DONE |
| `chunkCount` | N | update-status | set on DONE |
| `errorMessage` | S | update-status | set on FAILED, max 300 chars |
| `createdAt, updatedAt, startedAt` | S | create-upload / update-status / parse-event | ISO 8601 UTC |
| `processingMs` | N | update-status | DONE time minus startedAt |

Single-writer rule: M2 Lambdas never touch DynamoDB. Only M1 Lambdas write status fields.

## 9.6 JSON file formats

`text.json` (M1 writes, M2 reads). Audio: one segment per 30-second window (empty windows are dropped). PDF: one segment per page.

```json
{ "documentId": "...", "sourceType": "audio",
  "segments": [ {"text": "Welcome to the lecture...", "startSec": 0.0, "endSec": 30.0}, ... ] }
```

```json
{ "documentId": "...", "sourceType": "pdf",
  "segments": [ {"text": "Page one text...", "page": 1}, {"text": "...", "page": 2} ] }
```

`chunks.json` (M2). Unused fields are null.

```json
{ "documentId": "...", "sourceType": "audio",
  "chunks": [ {"chunkId": "<documentId>#0001", "text": "...",
         "startSec": 0.0, "endSec": 88.4, "pageStart": null, "pageEnd": null} ] }
```

`index.json` (M2). Same chunk fields plus `tf`, the term counts of that chunk. Tokenizer rule (both index and qa use it): lowercase, keep runs of a-z and 0-9, drop tokens shorter than 2 characters and the stop words listed in Doc 2 section 5.4.

```json
{ "documentId": "...", "fileName": "lecture1.wav", "sourceType": "audio", "method": "tfidf-v1",
  "chunks": [ {"chunkId": "...", "text": "...", "startSec": 0.0, "endSec": 88.4,
         "pageStart": null, "pageEnd": null, "tf": {"photosynthesis": 3, "light": 2}} ] }
```

## 9.7 Pipeline Lambda input and output

State machine context after parse-event: `{skip: false, userId, documentId, bucket, s3Key, fileName, fileType}`, or `{skip: true}`. M1 maps fields from the context into each Lambda input below (Step Functions Parameters). Lambdas return only the fields listed.

| Lambda | Owner | Input | Output |
|---|---|---|---|
| parse-event | M1 | EventBridge S3 "Object Created" event | context above |
| split-audio | M1 | `{userId, documentId, bucket, s3Key}` | `{windows: [{key, startSec, endSec}], windowCount}` |
| transcribe-window | M1 | `{userId, documentId, bucket, window: {key, startSec, endSec}}` | `{startSec, endSec, text}` |
| assemble-audio-text | M1 | `{userId, documentId, bucket, windows: [{startSec, endSec, text}]}` | `{textKey, segmentCount}` |
| extract-pdf | M1 | `{userId, documentId, bucket, s3Key}` | `{textKey, segmentCount}` |
| chunk | M2 | `{userId, documentId, bucket, textKey}` | `{chunksKey, chunkCount}` |
| summarize | M2 | `{userId, documentId, bucket, chunksKey}` | `{summary}` (plain text, max about 250 words). Also writes summary.txt |
| index | M2 | `{userId, documentId, bucket, chunksKey, fileName}` | `{indexKey, chunkCount}` |
| update-status | M1 | `{userId, documentId, status, step?, summary?, chunkCount?, errorMessage?}` | `{ok: true}` |

Failure rule: a Lambda signals failure by raising an exception with a clear message. The state machine catches it and calls update-status with FAILED. A temporary problem (HTTP 429 or 5xx from the model endpoint, network timeout) must raise an exception of a class named `ThrottlingException` so Step Functions retries it. A permanent problem (bad file, bad key) raises a plain `Exception` and is not retried.

## 9.8 API routes

All routes require a Cognito ID token in header `Authorization: Bearer <idToken>`. Success body is JSON. Error body is `{"error": "message"}` with status 400, 404 or 500. 401 comes from the authorizer.

| Route | Lambda (owner) | Request | Success response |
|---|---|---|---|
| POST `/uploads` | create-upload (M1) | `{fileName, contentType}` | `{documentId, uploadUrl, s3Key, expiresIn: 900}` |
| GET `/documents` | list-documents (M1) | none | `{documents: [item, ...]}` newest first |
| GET `/documents/{documentId}` | get-document (M1) | none | `{document: item, textUrl?}` (textUrl only when DONE, presigned GET for text.json, 15 min) |
| DELETE `/documents/{documentId}` | delete-document (M1) | none | `{deleted: true}` or 404 |
| POST `/ask` | qa (M2) | `{question, documentId?}` | `{answer, citations: [{documentId, fileName, label, snippet}]}` |
| POST `/speak` (optional) | speak (M2) | `{documentId}` | `{audioUrl, expiresIn: 900}` or 404 when no summary exists |

- The browser must PUT the file to uploadUrl with the same Content-Type it sent to `/uploads`.
- Citation label examples: 12:30-13:10 (audio) or p.4 / pp.4-5 (PDF).
- HTTP API hard integration timeout is 30 seconds. `/ask` must finish in under 25 seconds.
- Item = the DynamoDB attributes in section 9.5.
- `/speak` exists in the contract and the api stack from the start. M2 ships a stub in week 2. The UI shows the Listen button only when the real version is ready.

## 9.9 Lambda names

| Function (after `lecdoc-{stage}-`) | Owner | Folder |
|---|---|---|
| create-upload, list-documents, get-document, delete-document | M1 | `pipeline/src/<name_with_underscores>/app.py` |
| parse-event, split-audio, transcribe-window, assemble-audio-text, extract-pdf, update-status | M1 | `pipeline/src/<name_with_underscores>/app.py` |
| chunk, summarize, index, qa, speak | M2 | `ai/src/<name>/app.py` |

15 Lambdas in total. Handler is always `app.lambda_handler`. One IAM role per Lambda (SAM creates it when you give each function its own Policies). Least privilege.

## 9.10 Environment variables and identity

Every Lambda receives `STAGE` and `DATA_BUCKET`.
Pipeline Lambdas also receive `DOCUMENTS_TABLE`.
Model-calling Lambdas receive `MANTLE_BASE_URL` and `BEDROCK_KEY_PARAM`.
The transcription Lambda receives `STT_MODEL_ID`.
The summarize and QA Lambdas receive `TEXT_MODEL_ID`.
Values come from CloudFormation parameters or stack exports; they must never be hardcoded.
User identity must come from the JWT `sub` claim.
API responses must use a shared response helper so DynamoDB `Decimal` values serialize correctly.
