# Teardown

Run this after grading. Order matters: a stack whose export is in use cannot be deleted, so delete dependents first.
Always check the account before each block.

```bash
aws sts get-caller-identity --query Account --output text
# dev  = 149471050333  (AWS_PROFILE=lecdoc-dev)
# demo = 492613852256  (AWS_PROFILE=lecdoc-demo)
```

## 1. Stacks and data (per account)

```bash
export AWS_PROFILE=lecdoc-dev      # then repeat with lecdoc-demo
./infra/destroy.sh dev             # demo: ./infra/destroy.sh demo
```

`destroy.sh` empties the data and web buckets, deletes the stacks in the order monitoring, web, api, pipeline, ai, auth, core, and removes `/lecdoc/<stage>/bedrock-api-key` from SSM.
If a stack is stuck (DELETE_FAILED or ROLLBACK_COMPLETE), delete it by hand, then re-run the script or the workflow:

```bash
aws cloudformation delete-stack --stack-name lecdoc-<stage>-<name>
aws cloudformation wait stack-delete-complete --stack-name lecdoc-<stage>-<name>
```

## 2. Demo account only

```bash
export AWS_PROFILE=lecdoc-demo
aws cloudformation delete-stack --stack-name lecdoc-github-oidc      # last: CI uses this role
aws cloudformation wait stack-delete-complete --stack-name lecdoc-github-oidc
```

Also remove the repo's GitHub environment `demo` (secret `BEDROCK_API_KEY`, variables `ALERT_EMAIL`, `DEMO_DEPLOY_ROLE_ARN`).

## 3. SAM managed stack and its bucket (both accounts)

The bucket is versioned, so delete every version before the stack.

```bash
B=$(aws cloudformation describe-stack-resources --stack-name aws-sam-cli-managed-default \
    --query "StackResources[?ResourceType=='AWS::S3::Bucket'].PhysicalResourceId" --output text)
aws s3api list-object-versions --bucket "$B" --output json \
  --query '{Objects: [Versions,DeleteMarkers][][].{Key:Key,VersionId:VersionId}}' > /tmp/v.json
jq -e '.Objects|length>0' /tmp/v.json >/dev/null && aws s3api delete-objects --bucket "$B" --delete file:///tmp/v.json
aws cloudformation delete-stack --stack-name aws-sam-cli-managed-default
aws cloudformation wait stack-delete-complete --stack-name aws-sam-cli-managed-default
```

## 4. Log groups (both accounts)

```bash
for g in $(aws logs describe-log-groups --log-group-name-prefix /aws/lambda/lecdoc- --query 'logGroups[].logGroupName' --output text); do
  aws logs delete-log-group --log-group-name "$g"; done
for g in $(aws logs describe-log-groups --log-group-name-prefix /aws/vendedlogs --query 'logGroups[].logGroupName' --output text); do
  aws logs delete-log-group --log-group-name "$g"; done
```

## 5. Budgets

```bash
ACC=$(aws sts get-caller-identity --query Account --output text)
aws budgets describe-budgets --account-id $ACC --query 'Budgets[].BudgetName' --output text
aws budgets delete-budget --account-id $ACC --budget-name <name>     # demo: lecdoc-demo-monthly
```

## 6. Bedrock API keys (both accounts)

```bash
for u in $(aws iam list-users --query "Users[?starts_with(UserName,'BedrockAPIKey')].UserName" --output text); do
  for id in $(aws iam list-service-specific-credentials --user-name $u --service-name bedrock.amazonaws.com --query 'ServiceSpecificCredentials[].ServiceSpecificCredentialId' --output text); do
    aws iam delete-service-specific-credential --user-name $u --service-specific-credential-id $id; done
  for p in $(aws iam list-attached-user-policies --user-name $u --query 'AttachedPolicies[].PolicyArn' --output text); do
    aws iam detach-user-policy --user-name $u --policy-arn $p; done
  for p in $(aws iam list-user-policies --user-name $u --query 'PolicyNames' --output text); do
    aws iam delete-user-policy --user-name $u --policy-name $p; done
  aws iam delete-user --user-name $u
done
```

Each teammate also deletes the Bedrock key in their own account (Doc 0 step 8).

## 7. Demo read-only users (demo account)

```bash
for u in m1 m2 m4; do
  aws iam delete-login-profile --user-name $u 2>/dev/null
  for p in $(aws iam list-attached-user-policies --user-name $u --query 'AttachedPolicies[].PolicyArn' --output text); do
    aws iam detach-user-policy --user-name $u --policy-arn $p; done
  aws iam list-mfa-devices --user-name $u --query 'MFADevices[].SerialNumber' --output text | xargs -r -n1 aws iam deactivate-mfa-device --user-name $u --serial-number
  aws iam delete-user --user-name $u
done
```

## 8. Verify nothing is left

```bash
aws cloudformation list-stacks --query "StackSummaries[?StackStatus!='DELETE_COMPLETE'].StackName" --output text
aws s3 ls | grep lecdoc
aws dynamodb list-tables --query 'TableNames' --output text
aws ssm describe-parameters --parameter-filters Key=Name,Option=BeginsWith,Values=/lecdoc --query 'Parameters[].Name' --output text
aws lambda list-functions --query "Functions[?starts_with(FunctionName,'lecdoc')].FunctionName" --output text
```

All five must print nothing. Then check Billing for the next day to confirm no new charges.
