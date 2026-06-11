"""
파일 저장: 업로드 임시 저장 + S3(호환 스토리지) 업로드.
"""
import os

import aiofiles
import boto3
from fastapi import UploadFile

from core.config import S3_BUCKET, S3_ENDPOINT_URL, S3_REGION

s3_client = None
if S3_BUCKET:
    s3_client = boto3.client(
        "s3",
        region_name=S3_REGION,
        endpoint_url=S3_ENDPOINT_URL,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )


async def save_upload_to_path(file: UploadFile, path: str):
    """업로드 파일을 지정 경로에 비동기로 저장."""
    content = await file.read()
    async with aiofiles.open(path, "wb") as buffer:
        await buffer.write(content)


def upload_file_to_s3(local_path: str, key: str, content_type: str = "text/plain"):
    """저장된 파일을 S3(또는 호환 스토리지)로 업로드. 미설정 시 None."""
    if not s3_client or not S3_BUCKET:
        return None
    try:
        s3_client.upload_file(
            local_path,
            S3_BUCKET,
            key,
            ExtraArgs={"ContentType": content_type},
        )
        if S3_ENDPOINT_URL:
            base = S3_ENDPOINT_URL.rstrip("/")
            return f"{base}/{S3_BUCKET}/{key}"
        if S3_REGION:
            return f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{key}"
        return f"s3://{S3_BUCKET}/{key}"
    except Exception as e:
        print(f"S3 업로드 실패 ({local_path}): {e}")
        return None
