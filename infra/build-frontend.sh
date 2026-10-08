#!/usr/bin/env bash
# usage: ./infra/build-frontend.sh <dev|demo> (needs stacks api, auth, web deployed)
set -euo pipefail
cd "$(dirname "$0")/.."
STAGE=${1:?usage: build-frontend.sh dev|demo}
export AWS_DEFAULT_REGION=$(jq -r .region infra/config/$STAGE.json)
get() { aws cloudformation list-exports \
  --query "Exports[?Name=='lecdoc-$STAGE-$1'].Value" --output text; }
cat > frontend/app/public/config.js <<CFG
window.APP_CONFIG = {
  region: "$AWS_DEFAULT_REGION",
  apiUrl: "$(get ApiUrl)",
  userPoolId: "$(get UserPoolId)",
  clientId: "$(get UserPoolClientId)"
};
CFG
(cd frontend/app && npm ci && npm run build)
aws s3 sync frontend/app/dist "s3://$(get WebBucketName)" --delete
aws cloudfront create-invalidation --distribution-id "$(get CloudFrontDistributionId)" --paths "/*" > /dev/null
echo "Frontend live at $(get WebUrl)"
