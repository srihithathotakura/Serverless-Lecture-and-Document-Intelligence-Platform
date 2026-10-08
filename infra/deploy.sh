#!/usr/bin/env bash
# usage: ./infra/deploy.sh <dev|demo> [stack]
# stacks: core auth ai pipeline api web monitoring
set -euo pipefail
cd "$(dirname "$0")/.."
STAGE=${1:?usage: deploy.sh dev|demo [stack]}
ONLY=${2:-}
CFG=infra/config/$STAGE.json
export AWS_DEFAULT_REGION=$(jq -r .region "$CFG")
EMAIL=${ALERT_EMAIL:-$(jq -r .alertEmail "$CFG")}
TEXT_MODEL=$(jq -r .textModelId "$CFG")
STT_MODEL=$(jq -r .sttModelId "$CFG")
MANTLE_URL=$(jq -r .mantleBaseUrl "$CFG")
KEY_PARAM="/lecdoc/$STAGE/bedrock-api-key"

case "$STT_MODEL" in *FILL*|"") echo "Set sttModelId in $CFG (copy it from infra/checks/check_stt.sh)"; exit 1;; esac

echo "Account: $(aws sts get-caller-identity --query Account --output text) Stage: $STAGE"

want() { [ -z "$ONLY" ] || [ "$ONLY" = "$1" ]; }

cfn() { # name template owner [params...]
  local name=$1 tpl=$2 owner=$3; shift 3
  [ -f "$tpl" ] || { echo "skip $name (no $tpl)"; return 0; }
  want "$name" || return 0
  aws cloudformation deploy --stack-name "lecdoc-$STAGE-$name" --template-file "$tpl" \
    --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM --no-fail-on-empty-changeset \
    --tags project=lecdoc stage=$STAGE owner=$owner \
    --parameter-overrides Stage=$STAGE "$@"
}

sam_stack() { # name dir owner [params...]
  local name=$1 dir=$2 owner=$3; shift 3
  [ -f "$dir/template.yaml" ] || { echo "skip $name (no $dir/template.yaml)"; return 0; }
  want "$name" || return 0
  (cd "$dir" && sam build && sam deploy --stack-name "lecdoc-$STAGE-$name" --resolve-s3 \
    --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM --no-confirm-changeset --no-fail-on-empty-changeset \
    --tags "project=lecdoc stage=$STAGE owner=$owner" \
    --parameter-overrides Stage=$STAGE "$@")
}

secret() { # Bedrock API key goes to SSM, never into a template or a Lambda variable
  if [ -n "${BEDROCK_API_KEY:-}" ]; then
    aws ssm put-parameter --name "$KEY_PARAM" --type SecureString --value "$BEDROCK_API_KEY" --overwrite > /dev/null
    echo "Bedrock key stored in $KEY_PARAM"
  elif aws ssm get-parameter --name "$KEY_PARAM" > /dev/null 2>&1; then
    echo "Bedrock key parameter exists"
  else
    echo "ERROR: export BEDROCK_API_KEY (Doc 0 step 8) and run again"; exit 1
  fi
}

secret
cfn core infra/core.yaml m3 AlertEmail="$EMAIL"
cfn auth auth/template.yaml m4
sam_stack ai ai m2 TextModelId="$TEXT_MODEL" MantleBaseUrl="$MANTLE_URL"
sam_stack pipeline pipeline m1 SttModelId="$STT_MODEL" MantleBaseUrl="$MANTLE_URL"
cfn api api/template.yaml m4
cfn web frontend/template.yaml m4
if want web && [ -f frontend/app/package.json ]; then ./infra/build-frontend.sh "$STAGE"; fi
cfn monitoring infra/monitoring.yaml m3
echo "Deploy finished for stage $STAGE"
