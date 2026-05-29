import boto3
from fastapi import HTTPException
from botocore.exceptions import ClientError, NoCredentialsError
import os
from ..schemas import EmailRequest, EmailResponse
import logging
import os
from ..config import settings

AWS_ACCESS_KEY = settings.AWS_ACCESS_KEY_ID
AWS_SECRET_KEY = settings.AWS_SECRET_ACCESS_KEY

logger = logging.getLogger(__name__)

class SESService:
    def __init__(self):
        # HARD-CODED to ap-south-1 - no environment variables or config files
        try:
            # Clear any AWS environment variables that might interfere
            aws_env_vars = ['AWS_DEFAULT_REGION', 'AWS_REGION', 'AWS_PROFILE']
            for var in aws_env_vars:
                if var in os.environ:
                    del os.environ[var]
            
            # Create client with absolutely explicit configuration
            self.ses_client = boto3.client(
                'ses',
                region_name='ap-south-1',  # HARD-CODED
                aws_access_key_id=AWS_ACCESS_KEY,
                aws_secret_access_key=AWS_SECRET_KEY,
                config=boto3.session.Config(
                    region_name='ap-south-1',  # HARD-CODED again
                    signature_version='v4'
                )
            )
            
            # Configure from name and email
            self.from_name = "Learnogic"  # Custom display name
            self.default_from_email = "info@learnogic.com"
            
            # Verify the region
            actual_region = self.ses_client.meta.region_name
            logger.info(f"HARD-CODED SES client initialized for region: {actual_region}")
            
            if actual_region != 'ap-south-1':
                raise Exception(f"Failed to set region to ap-south-1, got {actual_region}")
            
            # Test the connection
            try:
                verified_emails = self.ses_client.list_verified_email_addresses()
                verified_list = verified_emails.get('VerifiedEmailAddresses', [])
                logger.info(f"Successfully connected to SES in ap-south-1")
                logger.info(f"Found {len(verified_list)} verified emails: {verified_list}")
                
                if 'info@learnogic.com' not in verified_list:
                    logger.warning("info@learnogic.com not in verified emails list")
                if 'jibing@nexonetics.com' not in verified_list:
                    logger.warning("jibing@nexonetics.com not in verified emails list")
                    
            except Exception as verify_e:
                logger.warning(f"Could not list verified emails during init (might lack permissions): {verify_e}")
                # Do not raise here; the user might only have ses:SendEmail permissions.
                
        except Exception as e:
            logger.error(f"Failed to initialize SES client: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to initialize AWS SES client: {str(e)}")

    def send_email(self, email_data: EmailRequest) -> EmailResponse:
        """Send email using AWS SES in ap-south-1"""
        try:
            logger.info(f"Attempting to send email from {email_data.from_address} to {email_data.to_addresses}")
            logger.info(f"Using SES client in region: {self.ses_client.meta.region_name}")
            
            # Double-check our verified emails before sending
            try:
                verified_response = self.ses_client.list_verified_email_addresses()
                verified_emails = verified_response.get('VerifiedEmailAddresses', [])
                logger.info(f"Current verified emails in {self.ses_client.meta.region_name}: {verified_emails}")
            except Exception as e:
                logger.warning(f"Could not double-check verified emails: {e}")
            
            # Prepare the email content
            destination = {
                'ToAddresses': [str(addr) for addr in email_data.to_addresses]
            }
            
            if email_data.cc_addresses:
                destination['CcAddresses'] = [str(addr) for addr in email_data.cc_addresses]
            
            if email_data.bcc_addresses:
                destination['BccAddresses'] = [str(addr) for addr in email_data.bcc_addresses]

            # Prepare message body
            body = {}
            if email_data.body_text:
                body['Text'] = {'Data': email_data.body_text, 'Charset': 'UTF-8'}
            if email_data.body_html:
                body['Html'] = {'Data': email_data.body_html, 'Charset': 'UTF-8'}
            
            if not body:
                raise ValueError("Either body_text or body_html must be provided")

            # Format the Source field with display name
            # Format: "Display Name <email@domain.com>"
            from_email = str(email_data.from_address)
            source = f"{self.from_name} <{from_email}>"
            
            logger.info(f"Sending email with Source: {source}")

            # Send the email
            response = self.ses_client.send_email(
                Source=source,  # Using formatted source with display name
                Destination=destination,
                Message={
                    'Subject': {'Data': email_data.subject, 'Charset': 'UTF-8'},
                    'Body': body
                }
            )

            logger.info(f"Email sent successfully from ap-south-1. MessageId: {response['MessageId']}")
            
            return EmailResponse(
                message_id=response['MessageId'],
                status="success",
                message="Email sent successfully from ap-south-1"
            )

        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            logger.error(f"AWS SES error: {error_code} - {error_message}")
            
            if error_code == 'MessageRejected':
                # Get debug info
                try:
                    verified_emails = self.ses_client.list_verified_email_addresses()
                    quota = self.ses_client.get_send_quota()
                    logger.error(f"Region: {self.ses_client.meta.region_name}")
                    logger.error(f"Verified emails: {verified_emails.get('VerifiedEmailAddresses', [])}")
                    logger.error(f"Send quota: {quota}")
                except Exception:
                    pass
                
                raise HTTPException(status_code=400, detail=f"Message rejected: {error_message}")
            else:
                raise HTTPException(status_code=500, detail=f"SES error: {error_message}")

        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            raise HTTPException(status_code=500, detail="Internal server error")
    
    def set_from_name(self, from_name: str):
        """Allow changing the from name dynamically"""
        self.from_name = from_name
        logger.info(f"From name updated to: {from_name}")