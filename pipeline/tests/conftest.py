import boto3
import pytest
from m1_helpers import BUCKET, TABLE
from moto import mock_aws


@pytest.fixture
def aws():
    """Mocked S3 bucket and documents table. Yields (s3 client, table resource)."""
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=BUCKET)
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.create_table(
            TableName=TABLE, BillingMode="PAY_PER_REQUEST",
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"},
                       {"AttributeName": "documentId", "KeyType": "RANGE"}],
            AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"},
                                  {"AttributeName": "documentId", "AttributeType": "S"}],
        )
        yield s3, table
