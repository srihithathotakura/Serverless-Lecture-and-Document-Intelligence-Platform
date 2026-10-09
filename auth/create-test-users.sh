#!/usr/bin/env bash
# usage: TEST_PASSWORD='YourPass123' ./auth/create-test-users.sh <dev|demo>
set -euo pipefail

STAGE=${1:?usage: create-test-users.sh dev|demo}
PW=${TEST_PASSWORD:?set TEST_PASSWORD}
export AWS_DEFAULT_REGION=us-east-1

POOL=$(aws cloudformation list-exports \
  --query "Exports[?Name=='lecdoc-$STAGE-UserPoolId'].Value" \
  --output text)

for u in user1 user2; do
  aws cognito-idp admin-create-user \
    --user-pool-id "$POOL" \
    --username "$u@lecdoc.test" \
    --message-action SUPPRESS \
    --user-attributes Name=email,Value="$u@lecdoc.test" Name=email_verified,Value=true || true

  aws cognito-idp admin-set-user-password \
    --user-pool-id "$POOL" \
    --username "$u@lecdoc.test" \
    --password "$PW" \
    --permanent
done

echo "Users created: user1@lecdoc.test user2@lecdoc.test"
