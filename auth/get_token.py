#!/usr/bin/env python3
import getpass
import os
import sys
import boto3
from botocore.exceptions import ClientError

REGION = "us-east-1"
USER_POOL_ID = "us-east-1_fW3wLKOgY"
CLIENT_ID = "3ujhjpff7dskd2hpgp0qdh2ldd"

username = input("Cognito username (e.g. user1@lecdoc.test): ").strip()
password = getpass.getpass("Cognito password: ")

client = boto3.client("cognito-idp", region_name=REGION)

try:
    response = client.admin_initiate_auth(
        UserPoolId=USER_POOL_ID,
        ClientId=CLIENT_ID,
        AuthFlow="ADMIN_USER_PASSWORD_AUTH",
        AuthParameters={
            "USERNAME": username,
            "PASSWORD": password,
        },
    )

    auth = response.get("AuthenticationResult")
    if not auth or not auth.get("IdToken"):
        print("Authentication needs an additional challenge.")
        print("Challenge:", response.get("ChallengeName", "unknown"))
        sys.exit(1)

    os.makedirs("auth", exist_ok=True)
    with open("auth/id_token.txt", "w", encoding="utf-8") as f:
        f.write(auth["IdToken"])
    os.chmod("auth/id_token.txt", 0o600)

    print("Authentication successful.")
    print("ID token saved to auth/id_token.txt (not displayed).")

except ClientError as e:
    print("Cognito authentication failed:", e.response["Error"]["Code"])
    print(e.response["Error"].get("Message", "No further details"))
    sys.exit(1)
