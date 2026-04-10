import boto3
from fastapi import APIRouter,FastAPI, HTTPException
from pydantic import BaseModel, EmailStr
from botocore.exceptions import ClientError, NoCredentialsError
import os
from typing import List, Optional
import logging
from ..utils.ses import SESService
from ..schemas import EmailRequest, EmailResponse
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/email", tags=["Email"])

# Initialize SES service
ses_service = SESService()

@router.post("/send-email", response_model=EmailResponse)
async def send_email(email_data: EmailRequest):
    """
    Send an email using AWS SES
    
    - **to_addresses**: List of recipient email addresses
    - **subject**: Email subject line
    - **body_text**: Plain text email body (optional if body_html is provided)
    - **body_html**: HTML email body (optional if body_text is provided)
    - **from_address**: Sender email address (must be verified in SES)
    - **cc_addresses**: List of CC email addresses (optional)
    - **bcc_addresses**: List of BCC email addresses (optional)
    """
    return ses_service.send_email(email_data)

@router.post("/send-test-email")
async def send_test_email():
    """
    Send a test email - useful for testing your SES setup
    """
    test_email = EmailRequest(
        to_addresses=["jibing@nexonetics.com"],  # Replace with your test email
        subject="Test Email from FastAPI + AWS SES",
        body_text="This is a test email sent from FastAPI using AWS SES!",
        body_html="""
        <html>
            <body>
                <h2>Test Email</h2>
                <p>This is a <strong>test email</strong> sent from FastAPI using AWS SES!</p>
                <p>If you received this, your SES integration is working correctly.</p>
            </body>
        </html>
        """,
        from_address="info@learnogic.com"  # Replace with your verified SES email
    )
    
    return ses_service.send_email(test_email)

@router.get("/email/debug")
async def debug_ses():
    """Debug SES configuration"""
    ses_service = SESService()
    
    try:
        # Check what region we're actually using
        region = ses_service.ses_client.meta.region_name
        
        # Get verified emails
        verified_response = ses_service.ses_client.list_verified_email_addresses()
        verified_emails = verified_response.get('VerifiedEmailAddresses', [])
        
        # Get quota
        quota = ses_service.ses_client.get_send_quota()
        
        return {
            "actual_region": region,
            "verified_emails": verified_emails,
            "quota": quota,
            "target_emails_verified": {
                "info@learnogic.com": "info@learnogic.com" in verified_emails,
                "jibing@nexonetics.com": "jibing@nexonetics.com" in verified_emails
            }
        }
    except Exception as e:
        return {"error": str(e)}