import aioboto3
from botocore.exceptions import ClientError
from app.core.config import settings
from typing import Tuple
from urllib.parse import urlparse


class S3Service:
    def __init__(self, bucket_name: str):
        self.bucket_name = bucket_name
        self.region = settings.S3_REGION
        self.access_key = settings.S3_ACCESS_KEY
        self.secret_key = settings.S3_SECRET_KEY

    async def get_file(self, key: str) -> Tuple[bytes, str]:
        session = aioboto3.Session()

        async with session.client(
            "s3",
            region_name=self.region,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
        ) as s3:
            try:
                response = await s3.get_object(Bucket=self.bucket_name, Key=key)
                content_type = response.get("ContentType", "application/octet-stream")
                content = await response["Body"].read()
                return content, content_type
            except ClientError as e:
                raise RuntimeError(f"S3 GetObject failed: {e}")

    def extract_key_from_url(self, url: str) -> str:
        parsed = urlparse(url)
        return parsed.path.lstrip("/")
