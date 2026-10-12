# M3: Infrastructure, DevOps and Monitoring

## 1. Why AWS SAM and CloudFormation
One IaC tool for every stack keeps the team on one syntax. SAM adds short Lambda syntax and `sam build` for packaging, while plain CloudFormation covers the buckets, table and alarms. Stacks are small and ordered (core, auth, ai, pipeline, api, web, monitoring) and talk only through CloudFormation exports, so each member can deploy their own stack without touching the others.

## 2. Why serverless
No servers to patch or size, cost is near zero while idle, and each piece (Lambda, Step Functions, API Gateway, DynamoDB, S3) scales by itself. Everything runs outside a VPC, so no NAT Gateway is needed. Services that cost money without a free tier (OpenSearch, NAT, RDS, EC2) were excluded.

## 3. Core stack
S3 data bucket (private, public access blocked, AES256 encryption, HTTPS-only bucket policy, 60-day lifecycle, EventBridge notifications), DynamoDB table `documents` (on-demand, encrypted, key userId + documentId) and an SNS alert topic. Outputs are exported under `lecdoc-{stage}-*` names that never change.

## 4. One-command deploy and teardown
`./infra/deploy.sh dev` (or `demo`) stores the Bedrock key in SSM, then deploys the stacks in order, skipping any whose template is missing. `./infra/destroy.sh` empties the buckets and deletes the stacks in reverse order. Stack tags: project, stage, owner. Teardown steps are in docs/teardown.md.

## 5. CI/CD
GitHub Actions workflow `ci.yml`: job `ci` (ruff, pytest, cfn-lint, secret scan) runs on pull requests and pushes. Job `deploy` runs only after a push to main, needs `ci`, and runs `./infra/deploy.sh demo`. Branch protection on main: pull request, 1 approval, Code Owners review, green `ci`, no force pushes. Secret scanning and push protection are on.
AWS access uses GitHub OIDC: no long-lived AWS keys in GitHub. The deploy role trusts only `repo:<org>/<repo>:*`. It has AdministratorAccess, accepted only because the demo account is dedicated to this project; a production setup would scope it to CloudFormation, IAM, Lambda, S3, DynamoDB, Step Functions and API Gateway actions.

## 6. Dev versus demo
Same templates and code, different stage name and account. Config lives in `infra/config/dev.json` and `demo.json`. Dev is deployed by hand in each member's account. Demo is deployed only by CI; nobody deploys it by hand. The alert email for demo comes from the GitHub variable ALERT_EMAIL.

## 7. Bedrock key handling
The key exists only in SSM Parameter Store as a SecureString `/lecdoc/{stage}/bedrock-api-key` and, for demo, as the GitHub environment secret BEDROCK_API_KEY. Only transcribe-window, summarize and qa can read it, each with `ssm:GetParameter` on that one parameter. It never appears in Git, templates or Lambda environment variables (only the parameter name does). Rotation: create a new key, update the GitHub secret, redeploy, delete the old key.
Evidence: SSM screenshot (SecureString), Lambda policy line, CI log line "Bedrock key stored".

## 7b. Account check scripts and samples
`infra/checks/` (Gemma, Polly, speech) let each member prove their account works before building. `samples/` holds WAV and PDF test files plus a scanned PDF for the failure test.

## 8. Monitoring
CloudWatch dashboard `lecdoc-{stage}`: Lambda errors (15 functions), Lambda duration p95, pipeline executions, average processing time, API latency and 4xx/5xx, AI tokens per hour (Logs Insights over `AI_USAGE` log lines). Alarms: `pipeline-failed` (Step Functions ExecutionsFailed >= 1) and `api-5xx` (>= 5 in 5 minutes), both notify the SNS topic, which emails the team. A failed document ends its execution in a Fail state so the alarm fires.
Evidence: dashboard screenshot, alarm email screenshot.

## 9. Performance and cost
Measured in the dev account on 2026-10-11, because the demo account has no UI stack; the tables are in docs/perf/latency.md.

**API latency.** From a client in India over WSL, with a new TLS connection per call, GET /documents had p50 919 ms and p95 1127 ms over 50 sequential calls, and p50 949 ms and p95 1122 ms over 5 parallel batches of 10, with no errors. Most of this is the network round trip and the TLS handshake: CloudWatch shows API Gateway server-side latency of p50 66 ms and p95 450 ms across all routes. POST /ask, which includes one Gemma call, had p50 1376 ms and p95 1459 ms over 5 calls.

**Processing time versus length.** Each file was processed once. Audio of 1, 3 and 4.9 minutes took 7.2, 6.9 and 10.8 seconds. PDFs of 2, 10 and 20 pages took 4.8, 3.0 and 3.5 seconds. Audio time should grow with the number of 30-second windows, which run two at a time, but single runs include Lambda cold starts, so only the 4.9-minute file clearly stands out. PDF time is dominated by the summary model call and barely grows with page count.

**Cost per document.** Prices were read from the Bedrock and Polly pricing pages on 2026-10-10. A 5-minute lecture costs about $0.0074 with the optional Polly summary and $0.0015 without. A 20-page PDF costs about $0.0065 with Polly and $0.0005 without. The speech figure is an upper bound because only audio seconds are logged, not model usage tokens. Token counts come from M2.

## 10. Limits
WAV only (16-bit PCM, up to 5 minutes), text PDFs only (up to 20 pages), keyword (TF-IDF) search only. Fixed 30-second audio windows can cut words at the edges. AdministratorAccess on the demo deploy role is a documented trade-off.

## 11. Testing and evidence
- ruff, pytest, cfn-lint and the secret scan run on every pull request. To prove the scan works, a test PR containing a fake AWS key string turned `ci` red and was closed unmerged.
- The alarm path was tested end to end: setting the pipeline alarm state by hand produced the email through the SNS topic. The dev state machine has both successful and failed executions, so the failure path is exercised too.
- Destroy and redeploy were run in a dev account to confirm that a clean account needs only BEDROCK_API_KEY and ALERT_EMAIL.
- Evidence screenshots: SSM parameter (SecureString, value hidden), CI log line "Bedrock key stored", CloudFormation stack list, dashboard with real traffic, Step Functions run with the Map state, successful Actions run, and the budget and IAM users in the demo account.

## 12. Challenges and trade-offs
- The demo account is a separate AWS account with its own 10 USD budget and its own Bedrock key. The key exists only as a GitHub environment secret and in SSM, and its expiry date is checked weekly.
- CloudFront was not verified in the demo account, so the deploy script reads a skipStacks setting from the stage config and skips the web stack there, without changing any template.
- Free-plan accounts could not call Transcribe, Textract or Comprehend, so every component was tested on a real account before it was chosen.
