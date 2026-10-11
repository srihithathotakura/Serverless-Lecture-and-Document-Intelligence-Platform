#!/usr/bin/env python3
"""Print a Cognito ID token for a specified stage and test user."""
import os
import sys

import boto3


def main():
    if len(sys.argv) != 3:
        sys.exit("Usage: python tests/get_token.py <stage> <email>")

    stage, email = sys.argv[1], sys.argv[2]
    password = os.environ.get("TEST_PASSWORD")
    if not password:
        sys.exit("Set TEST_PASSWORD in the environment; never put it in this file.")

    region = os.environ.get("AWS_REGION", "us-east-1")
    cf = boto3.client("cloudformation", region_name=region)
    exports = {
        item["Name"]: item["Value"]
        for page in cf.get_paginator("list_exports").paginate()
        for item in page["Exports"]
    }

    prefix = f"lecdoc-{stage}-"
    pool_id = exports.get(prefix + "UserPoolId")
    client_id = exports.get(prefix + "UserPoolClientId")
    if not pool_id or not client_id:
        sys.exit(f"Missing Cognito CloudFormation exports for stage: {stage}")

    cognito = boto3.client("cognito-idp", region_name=region)
    result = cognito.admin_initiate_auth(
        UserPoolId=pool_id,
        ClientId=client_id,
        AuthFlow="ADMIN_USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": email, "PASSWORD": password},
    )
    print(result["AuthenticationResult"]["IdToken"])


if __name__ == "__main__":
    main()
