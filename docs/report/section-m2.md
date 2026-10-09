# Section M2 - AI and data

Owner: M2. Stack lecdoc-{stage}-ai. Code in ai/. Lambda names: lecdoc-{stage}-chunk,
-summarize, -index, -qa, -speak (per Doc 0 9.1 / docs/contracts.md).

## 1. Overview

    chunk (state machine step)
      input: {userId, documentId, bucket, textKey}
      reads processed/{userId}/{documentId}/text.json
      groups segments into ~500-char chunks, chunkId format <documentId>#0001
      output always has all 4 fields (startSec/endSec/pageStart/pageEnd), unused ones null
      writes processed/{userId}/{documentId}/chunks.json
      output: {chunksKey, chunkCount}

    index (state machine step)
      input: {userId, documentId, bucket, chunksKey, fileName}
      reads chunks.json, computes per-chunk term frequency (tf)
      writes processed/{userId}/{documentId}/index.json
      shape: {documentId, fileName, sourceType, method: "tfidf-v1", chunks: [...with tf]}
      output: {indexKey, chunkCount}

    summarize (state machine step)
      input: {userId, documentId, bucket, chunksKey}
      reads chunks.json, one Bedrock call (Gemma) for a plain-text summary (<=250 words)
      writes processed/{userId}/{documentId}/summary.txt
      output: {summary}

    qa (POST /ask, on demand - not a pipeline step)
      input: {question, documentId} (direct invoke or API Gateway proxy body)
      reads index.json, ranks chunks by tf-idf against the question, takes top 3,
      sends them as context to Bedrock (Gemma)
      output: {answer, citations: [{documentId, fileName, label, snippet}]}
      label is MM:SS-MM:SS for audio or p.N / pp.N-M for pdf

    speak (POST /speak, on demand - not a pipeline step)
      input: {documentId} only
      reads the existing processed/{userId}/{documentId}/summary.txt (no summary -> error)
      synthesizes it via Polly, writes processed/{userId}/{documentId}/summary.mp3
      output: {audioUrl, expiresIn: 900} (presigned GET url)

chunk, summarize and index are invoked by the M1 state machine as pipeline steps.
qa and speak are the M2-owned API routes, invoked directly or (once the M4 api stack
exists) through API Gateway - both parse_request() functions handle either shape.

## 2. docs/contracts.md arrived after the first implementation

The first working version of all 5 Lambdas (deployed and demoed in dev) used its own,
reasonable-but-undocumented shapes: documents/{documentId}/... S3 paths, c0000-style
chunk ids, a plain inverted keyword index with no tf, a qa response with no citations,
and a speak that took arbitrary text and returned raw byte counts. docs/contracts.md
(Doc 0 section 9, frozen and pending M3 review) was added to the repo partway through
this work and specifies different, more complete shapes - notably real tf-idf scoring,
citations with timestamps/page numbers, and the /ask and /speak API contract.
Everything in section 1 above reflects the second, contract-matching rewrite. The
rewrite was necessary rather than additive: field names, S3 paths, and function
signatures all changed, which is also why the unit test suite needed a full rewrite
alongside it (18 of the original tests referenced the old shapes).

## 3. Why tf-idf instead of a plain inverted index

- A plain word -> chunk-ids index (the first version) can find which chunks contain a
  query word, but cannot rank them by relevance when several chunks all mention it -
  common in a short, single-topic lecture.
- tf-idf (the contracts.md 9.6 "tfidf-v1" method) scores each chunk by how often a query
  term appears in it, discounted by how many chunks share that term, so a chunk that
  specifically elaborates on the question ranks above one that just mentions the topic
  in passing.
- Known limit: still purely lexical, computed per-document (not across a corpus) - a
  question using different words than the source text can still miss the right chunk.
  Acceptable at this scale (a handful of chunks per lecture); embeddings would be
  needed to scale further.

## 4. A real bug: unsmoothed idf collapses on short documents

The standard idf formula, log(N / (1 + df)), goes to zero whenever a term appears in
every chunk of a small document - exactly the case for a short lecture main topic
word, which tends to recur throughout. The first implementation used the plain formula
and silently returned zero citations for on-topic questions. Fixed with the standard
smoothed variant, log((N+1) / (1+df)) + 1, which stays positive even when a term
appears in all chunks. Caught by testing against the real photosynthesis fixture,
where "calvin" and "cycle" each appeared in 3 of 4 chunks.

## 5. Bedrock key handling

Same pattern as M1 transcribe-window: the key lives only in SSM Parameter Store
(/lecdoc/{stage}/bedrock-api-key, SecureString), fetched once per container and cached
in memory, never in an environment variable, the template, or Git. CloudFormation
cannot resolve an ssm-secure dynamic reference directly into a Lambda environment
variable (tried and rejected by the deploy), so the parameter name (env var
BEDROCK_KEY_PARAM, per contracts.md 9.10) is passed and the Lambda fetches the value
itself at runtime via ssm:GetParameter.

## 6. IAM (one role per Lambda)

| Lambda | Actions | Resources |
| --- | --- | --- |
| chunk | s3:GetObject, PutObject (S3CrudPolicy) | data bucket |
| index | s3:GetObject, PutObject (S3CrudPolicy) | data bucket |
| summarize | s3:GetObject, PutObject; ssm:GetParameter | data bucket; parameter/lecdoc/{stage}/bedrock-api-key |
| qa | s3:GetObject, PutObject; ssm:GetParameter | data bucket; parameter/lecdoc/{stage}/bedrock-api-key |
| speak | s3:GetObject, PutObject; polly:SynthesizeSpeech | data bucket; * (Polly has no resource-level permissions) |

S3CrudPolicy currently scopes to the whole data bucket rather than a processed/* prefix
like the M1 pipeline roles - a tightening worth doing to match that pattern.

## 7. Bugs found and fixed during deployment

- us-east-1 global S3 endpoint redirect. The data bucket was recreated several times
  during environment setup; afterward the Lambda S3 client failed with PermanentRedirect
  even though the AWS CLI worked fine against the same bucket (legacy global
  s3.amazonaws.com endpoint versus the regional one). Fixed by setting
  AWS_S3_US_EAST_1_REGIONAL_ENDPOINT=regional on all five functions.
- ssm-secure dynamic reference not supported in Lambda env vars (section 5).
- qa had a stale SSM key reference after summarize was switched to the SSM pattern but
  qa was not updated at the same time - would have failed at first real invocation.
- Unsmoothed tf-idf (section 4).
- FunctionName could not simply be added: contracts.md 9.1 requires fixed names, but
  adding FunctionName forces CloudFormation to replace each Lambda, and
  lecdoc-{stage}-pipeline imports the ai stack ARN exports - CloudFormation refuses to
  delete an export still in use. M3 confirmed this was a genuine bug (not a contract
  change) and gave the rollout: delete the pipeline stack, redeploy ai (now unblocked
  since nothing imports its exports), redeploy pipeline (recreates cleanly against the
  new fixed-name ARNs). Done in dev; M3 to repeat the same two-stack cutover in demo
  once this merges, since CI there will otherwise fight the same export lock.

## 8. Performance

Measured in the dev account against the deployed lecdoc-dev-{chunk,summarize,index,qa,
speak} functions, direct CLI invocation, warm containers (see docs/perf/ai-timings.csv):

| Function | Operation | Wall time (s) |
| --- | --- | --- |
| chunk | chunk a 4-segment audio doc | 1.39 |
| index | build tf-idf index from 4 chunks | 1.42 |
| summarize | summarize 4 chunks via Gemma, write summary.txt | 2.81 |
| qa | answer a question, tf-idf-ranked 3-chunk context via Gemma | 1.92 |
| speak | read summary.txt, synthesize via Polly, return presigned url | 2.39 |

- chunk and index are fast and dominated by the Lambda invoke round trip - no model
  call.
- summarize, qa and speak all call an external service (Bedrock or Polly) and are
  correspondingly slower; summarize is the slowest since it sends the most text
  (all chunks combined, not just the top 3 like qa) and reads max_tokens=300 versus
  qa 200.
- These are CLI wall-clock times (invoke plus network), not Lambda billed duration, so
  they run a bit higher than the M1 processingMs figures - comparable in shape, not
  value.

## 9. Testing

- Unit tests (pytest ai/): moto mocks S3 and SSM; Bedrock and Polly calls are mocked via
  monkeypatch (no AWS mock exists for the Mantle endpoint or deterministic Polly audio).
  25 tests covering: chunk boundary and null-field correctness for audio and pdf inputs,
  chunkId format (<documentId>#0001), tokenization and tf-idf scoring (including the
  smoothing fix from section 4), citation label formatting for both audio and pdf,
  summarize writing summary.txt with the correct content type, speak reading an
  existing summary and erroring cleanly when none exists, SSM key fetch-and-cache
  behaviour, API-Gateway-style body parsing for both qa and speak, and S3
  read/write correctness throughout.
- End-to-end runs in the dev account: all five functions invoked directly against real
  S3 data under their final fixed names (lecdoc-dev-chunk etc) - chunk, index,
  summarize, qa and speak each confirmed working with real Bedrock and Polly responses,
  correct S3 writes, and a real presigned audioUrl from speak (section 8 timings are
  from these runs).
- Not yet tested: the AI Lambdas invoked as part of the actual M1 state machine (only
  tested via direct invoke, not through a real pipeline upload) and the /ask and /speak
  routes through actual API Gateway (the M4 api stack does not exist yet, so qa and
  speak API-Gateway-body parsing path is covered by unit tests only, not a live call).
