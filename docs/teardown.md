# Teardown (M3)

Run after final grading. Serverless idle cost is near zero, but S3 data and CloudWatch logs persist until deleted.

## 1. Dev account (each member, own account)
```bash
export AWS_PROFILE=lecdoc-dev
aws sts get-caller-identity            # confirm it is YOUR account, not demo
./infra/destroy.sh dev                 # type yes; empties both buckets, deletes stacks in reverse order, deletes the SSM key
```

## 2. Demo account (M3 only, from the demo profile)
```bash
export AWS_PROFILE=lecdoc-demo
aws sts get-caller-identity            # must show the demo account ID
./infra/destroy.sh demo                # type yes
aws cloudformation delete-stack --stack-name lecdoc-github-oidc   # removes OIDC provider and deploy role
aws cloudformation wait stack-delete-complete --stack-name lecdoc-github-oidc
```

## 3. Verify nothing is left
```bash
aws cloudformation list-stacks --query "StackSummaries[?starts_with(StackName,'lecdoc') && StackStatus!='DELETE_COMPLETE'].StackName" --output text
aws s3 ls | grep lecdoc
aws ssm describe-parameters --parameter-filters Key=Name,Option=BeginsWith,Values=/lecdoc/ --query 'Parameters[].Name' --output text
aws logs describe-log-groups --log-group-name-prefix /aws/lambda/lecdoc --query 'logGroups[].logGroupName' --output text
```
All four must print nothing. Delete leftover log groups with `aws logs delete-log-group --log-group-name <name>`.

## 4. Keys and accounts
- Bedrock console, API keys: delete every key created for this project (each member's and the demo key).
- IAM: delete the access keys of dev-admin users; remove demo users m1, m2, m4.
- GitHub: delete the environment secret BEDROCK_API_KEY (Settings, Environments, demo) and the variables DEMO_DEPLOY_ROLE_ARN, ALERT_EMAIL.
- Billing: keep the budget alarms until the final bill shows zero, then delete them. Close the demo account if the team no longer needs it (Account, Close account).

## 5. What can cost money if left running
| Item | Why |
|---|---|
| S3 data bucket | stored uploads and processed text (60-day lifecycle rule is a safety net) |
| CloudWatch logs and dashboard | log storage; the first 3 dashboards are free |
| Bedrock API key | no cost while idle, but a leaked key can be abused: delete it |

## 6. Re-deploy after a teardown
`export BEDROCK_API_KEY=... ALERT_EMAIL=...` then `./infra/deploy.sh dev`. The deploy script recreates the SSM key.
