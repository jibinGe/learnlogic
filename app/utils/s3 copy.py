# utils/s3.py
import boto3
import uuid
from fastapi import UploadFile
from botocore.exceptions import ClientError
from ..config import settings

class S3Client:
    def __init__(self):
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION
        )
        self.bucket_name = settings.AWS_BUCKET_NAME

    def upload_file(self, file: UploadFile) -> str:
        """Upload a file to S3 bucket and return its URL"""
        try:
            # Generate unique filename
            file_extension = file.filename.split('.')[-1]
            unique_filename = f"{uuid.uuid4()}.{file_extension}"
            
            # Upload file to S3
            self.s3_client.upload_fileobj(
                file.file,
                self.bucket_name,
                f"testimonials/{unique_filename}",
                ExtraArgs={
                    "ContentType": file.content_type
                }
            )
            
            # Generate URL
            url = f"https://{self.bucket_name}.s3.{settings.AWS_REGION}.amazonaws.com/testimonials/{unique_filename}"
            return url
            
        except ClientError as e:
            print(f"Error uploading file to S3: {e}")
            raise
        finally:
            file.file.close()

    def upload_file_obj(self, file_obj, object_name, content_type=None):
        """
        Upload a file-like object to an S3 bucket
        
        :param file_obj: File-like object to upload
        :param object_name: S3 object name (with path)
        :param content_type: Content type of the file
        :return: Public URL of the uploaded file
        """
        try:
            extra_args = {}
            if content_type:
                extra_args['ContentType'] = content_type
            
            # Upload the file object
            self.s3_client.upload_fileobj(
                file_obj,
                self.bucket_name,
                object_name,
                ExtraArgs=extra_args
            )
            
            # Generate and return the URL
            # Use settings.AWS_REGION instead of self.region
            url = f"https://{self.bucket_name}.s3.{settings.AWS_REGION}.amazonaws.com/{object_name}"
            return url
        except Exception as e:
            print(f"Error in upload_file_obj: {e}")
            raise