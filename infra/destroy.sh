#!/usr/bin/env bash
# usage: ./infra/destroy.sh <dev|demo>
set -euo pipefail
cd "$(dirname "$0")/.."
STAGE=${1:?usage: destroy.sh dev|demo}
export AWS_DEFAULT_REGION=$(jq -r .region infra/config/$STAGE.json)
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
read -p "Delete ALL lecdoc-$STAGE stacks in account $ACCOUNT? Type yes: " ok
[ "$ok" = yes ] || exit 1
for b in "lecdoc-$STAGE-data-$ACCOUNT" "lecdoc-$STAGE-web-$ACCOUNT"; do
  aws s3 rm "s3://$b" --recursive 2>/dev/null || true
done
for s in monitoring web api pipeline ai auth core; do
  aws cloudformation delete-stack --stack-name "lecdoc-$STAGE-$s"
  aws cloudformation wait stack-delete-complete --stack-name "lecdoc-$STAGE-$s"
done
aws ssm delete-parameter --name "/lecdoc/$STAGE/bedrock-api-key" 2>/dev/null || true
echo "Destroyed stage $STAGE"
