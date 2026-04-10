# utils/s3.py
import boto3
import uuid
from fastapi import UploadFile
from botocore.exceptions import ClientError
from ..config import settings
from typing import Dict, Any, Optional
import json

class S3Client:
    def __init__(self):        
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION
        )
        self.bucket_name = settings.AWS_BUCKET_NAME

    def generate_presigned_url(
        self, 
        object_key: str, 
        content_type: str,
        expiration: int = 3600,
        max_file_size: int = 10 * 1024 * 1024 * 1024  # 10GB default
    ) -> Dict[str, Any]:
        """
        Generate a presigned URL for uploading files directly to S3
        
        :param object_key: S3 object key (path where file will be stored)
        :param content_type: MIME type of the file
        :param expiration: URL expiration time in seconds (default 1 hour)
        :param max_file_size: Maximum allowed file size in bytes
        :return: Dictionary containing presigned URL with all parameters included
        """
        try:
            # Use presigned URL for PUT operation (simpler than POST)
            presigned_url = self.s3_client.generate_presigned_url(
                'put_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': object_key,
                    'ContentType': content_type
                },
                ExpiresIn=expiration
            )
            
            # The presigned URL now contains all required parameters
            final_url = f"https://{self.bucket_name}.s3.{settings.AWS_REGION}.amazonaws.com/{object_key}"
            
            return {
                "presigned_url": presigned_url,  # This now includes all query parameters
                "fields": {},  # Empty for PUT requests
                "object_key": object_key,
                "final_url": final_url,
                "method": "PUT",  # Indicate this should be a PUT request
                "content_type": content_type  # For reference
            }
            
        except ClientError as e:
            print(f"Error generating presigned URL: {e}")
            raise

    def generate_presigned_post_url(
        self, 
        object_key: str, 
        content_type: str,
        expiration: int = 3600,
        max_file_size: int = 10 * 1024 * 1024 * 1024  # 10GB default
    ) -> Dict[str, Any]:
        """
        Generate a presigned POST URL (original method with form fields)
        Keep this for backward compatibility or when form upload is preferred
        """
        try:
            # Generate presigned POST URL with conditions
            conditions = [
                {"Content-Type": content_type},
                ["content-length-range", 1, max_file_size],  # Min 1 byte, max as specified
                {"bucket": self.bucket_name}
            ]
            
            fields = {
                "Content-Type": content_type
            }
            
            presigned_post = self.s3_client.generate_presigned_post(
                Bucket=self.bucket_name,
                Key=object_key,
                Fields=fields,
                Conditions=conditions,
                ExpiresIn=expiration
            )
            
            # Force the correct region-specific URL
            region_specific_url = f"https://{self.bucket_name}.s3.{settings.AWS_REGION}.amazonaws.com/"
            
            return {
                "presigned_url": region_specific_url,
                "fields": presigned_post["fields"],
                "object_key": object_key,
                "final_url": f"https://{self.bucket_name}.s3.{settings.AWS_REGION}.amazonaws.com/{object_key}",
                "method": "POST"
            }
            
        except ClientError as e:
            print(f"Error generating presigned URL: {e}")
            raise

    def initiate_multipart_upload(
        self, 
        object_key: str, 
        content_type: str
    ) -> Dict[str, str]:
        """
        Initiate multipart upload for large files
        
        :param object_key: S3 object key
        :param content_type: MIME type of the file
        :return: Upload ID and object key
        """
        try:
            response = self.s3_client.create_multipart_upload(
                Bucket=self.bucket_name,
                Key=object_key,
                ContentType=content_type
            )
            
            return {
                "upload_id": response["UploadId"],
                "object_key": object_key
            }
            
        except ClientError as e:
            print(f"Error initiating multipart upload: {e}")
            raise

    def generate_presigned_url_for_part(
        self,
        object_key: str,
        upload_id: str,
        part_number: int,
        expiration: int = 3600
    ) -> str:
        """
        Generate presigned URL for uploading a specific part in multipart upload
        
        :param object_key: S3 object key
        :param upload_id: Multipart upload ID
        :param part_number: Part number (1-based)
        :param expiration: URL expiration time in seconds
        :return: Presigned URL for the part
        """
        try:
            presigned_url = self.s3_client.generate_presigned_url(
                'upload_part',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': object_key,
                    'UploadId': upload_id,
                    'PartNumber': part_number
                },
                ExpiresIn=expiration
            )
            
            return presigned_url
            
        except ClientError as e:
            print(f"Error generating presigned URL for part: {e}")
            raise

    def complete_multipart_upload(
        self,
        object_key: str,
        upload_id: str,
        parts: list
    ) -> str:
        """
        Complete multipart upload
        
        :param object_key: S3 object key
        :param upload_id: Multipart upload ID
        :param parts: List of parts with ETag and PartNumber
        :return: Final object URL
        """
        try:
            response = self.s3_client.complete_multipart_upload(
                Bucket=self.bucket_name,
                Key=object_key,
                UploadId=upload_id,
                MultipartUpload={'Parts': parts}
            )
            
            return f"https://{self.bucket_name}.s3.{settings.AWS_REGION}.amazonaws.com/{object_key}"
            
        except ClientError as e:
            print(f"Error completing multipart upload: {e}")
            raise

    def abort_multipart_upload(
        self,
        object_key: str,
        upload_id: str
    ) -> bool:
        """
        Abort multipart upload (cleanup on failure)
        
        :param object_key: S3 object key
        :param upload_id: Multipart upload ID
        :return: Success status
        """
        try:
            self.s3_client.abort_multipart_upload(
                Bucket=self.bucket_name,
                Key=object_key,
                UploadId=upload_id
            )
            return True
            
        except ClientError as e:
            print(f"Error aborting multipart upload: {e}")
            return False

    def delete_object(self, object_key: str) -> bool:
        """
        Delete an object from S3
        
        :param object_key: S3 object key to delete
        :return: Success status
        """
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=object_key
            )
            return True
            
        except ClientError as e:
            print(f"Error deleting object: {e}")
            return False

    # Keep existing methods for backward compatibility
    def upload_file(self, file: UploadFile) -> str:
        """Upload a file to S3 bucket and return its URL (legacy method)"""
        try:
            file_extension = file.filename.split('.')[-1]
            unique_filename = f"{uuid.uuid4()}.{file_extension}"
            
            self.s3_client.upload_fileobj(
                file.file,
                self.bucket_name,
                f"testimonials/{unique_filename}",
                ExtraArgs={
                    "ContentType": file.content_type
                }
            )
            
            url = f"https://{self.bucket_name}.s3.{settings.AWS_REGION}.amazonaws.com/testimonials/{unique_filename}"
            return url
            
        except ClientError as e:
            print(f"Error uploading file to S3: {e}")
            raise
        finally:
            file.file.close()

    def upload_file_obj(self, file_obj, object_name, content_type=None):
        """Upload a file-like object to an S3 bucket (legacy method)"""
        try:
            extra_args = {}
            if content_type:
                extra_args['ContentType'] = content_type
            
            self.s3_client.upload_fileobj(
                file_obj,
                self.bucket_name,
                object_name,
                ExtraArgs=extra_args
            )
            
            url = f"https://{self.bucket_name}.s3.{settings.AWS_REGION}.amazonaws.com/{object_name}"
            return url
        except Exception as e:
            print(f"Error in upload_file_obj: {e}")
            raise