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
GitHub Actions workflow `main`: job `ci` (ruff, pytest, cfn-lint, secret scan) runs on pull requests and pushes. Job `deploy` runs only after a push to main, needs `ci`, and runs `./infra/deploy.sh demo`. Branch protection on main: pull request, 1 approval, Code Owners review, green `ci`, no force pushes. Secret scanning and push protection are on.
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
See docs/perf/latency.md: API latency table, processing time versus length, cost per document (5-minute lecture and 20-page PDF).

## 10. Limits
WAV only (16-bit PCM, up to 5 minutes), text PDFs only (up to 20 pages), keyword (TF-IDF) search only. Fixed 30-second audio windows can cut words at the edges. AdministratorAccess on the demo deploy role is a documented trade-off.
