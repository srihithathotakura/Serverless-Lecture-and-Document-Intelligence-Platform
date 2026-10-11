# Security Review — Week 5

## Scope

Read-only IAM review of the 15 deployed Lambda functions in `us-east-1`.
No AWS resources or deployed policies were modified.

## Findings

### 1. Broad S3 permissions on AI Lambdas

**Affected functions:** `chunk`, `summarize`, `index`, `qa`, `speak`

These functions use `S3CrudPolicy`, which grants a broad set of S3 actions against the data bucket and its objects. The observed application code uses narrower S3 operations.

**Recommendation:** Review each function's complete code paths and reduce permissions to the required actions and object prefixes. Validate the revised policies with tests before deployment.

**Status:** Least-privilege improvement identified; policy changes not applied.

### 2. Bedrock API-key parameter access

The `summarize`, `qa`, and `transcribe-window` functions have `ssm:GetParameter` permission scoped to the specific Bedrock API-key parameter.

**Assessment:** Resource scope is appropriately narrow. Keep the permission restricted to that parameter.

### 3. Delete-document S3 permissions

The `delete-document` function has `s3:ListBucket` restricted by the `s3:prefix` condition to `uploads/*` and `processed/*`. Its `s3:DeleteObject` permission is restricted to those object prefixes. The application further limits deletion to the requesting user's document paths.

**Assessment:** No immediate policy change identified from the reviewed statements.

### 4. Polly speech synthesis

The `speak` function has `polly:SynthesizeSpeech` with `Resource: "*"`.

**Assessment:** This is not reported as a defect without evidence that the action supports resource-level restrictions. Verify against the current Amazon Polly service authorization reference before proposing a change.

### 5. Pipeline Lambda permissions

The reviewed pipeline policies generally restrict S3 access to upload or processed-object prefixes and grant DynamoDB access to the documents table as needed.

**Recommendation:** Preserve these restrictions and validate permissions against each function's code paths.

## Summary and next actions

1. Review and narrow S3 permissions for the five AI functions.
2. Confirm required actions and prefixes with each function owner.
3. Test proposed policy changes before deployment.
4. Keep deployed policies unchanged until the changes are reviewed and approved.

## Limitations

This was a read-only review of selected deployed IAM policy statements and application code paths. Findings are least-privilege recommendations, not proof of exploitable vulnerabilities. This document does not claim that every statement or execution path has undergone a complete security assessment.
