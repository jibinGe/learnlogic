# In your user router file
import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..utils.ses import SESService
from app import schemas
from ..database import get_db
from app import models
from ..schemas import EmailRequest
import logging
from .. import auth


router = APIRouter(prefix="/password", tags=["Password"])
ses_service = SESService()
logger = logging.getLogger(__name__)

@router.post("/password-reset-request")
def request_password_reset(
    request: schemas.PasswordResetRequest, 
    db: Session = Depends(get_db)
):
    """Send password reset email with token"""
    
    # Find user by email
    user = db.query(models.User).filter(models.User.email == request.email).first()
    
    if not user:
        # For security, don't reveal if email exists or not
        # Return success message anyway
        return {
            "message": "Email address not found. Please try again."
        }
    
    # Generate secure token
    reset_token = secrets.token_urlsafe(32)
    
    # Set token expiration (e.g., 1 hour from now)
    expires_at = datetime.utcnow() + timedelta(hours=1)
    
    # Delete any existing unused tokens for this user
    db.query(models.PasswordResetToken).filter(
        models.PasswordResetToken.user_id == user.id,
        models.PasswordResetToken.used == False
    ).delete()
    
    # Create new reset token
    db_token = models.PasswordResetToken(
        user_id=user.id,
        token=reset_token,
        expires_at=expires_at,
        used=False
    )
    db.add(db_token)
    db.commit()
    
    # Create password reset link (update with your frontend URL)
    reset_link = f"https://learnogic.com/reset-password?token={reset_token}"
    
    # Send email with reset link
    try:
        reset_email = EmailRequest(
            to_addresses=[user.email],
            subject="Password reset request",
            body_text=f"""Dear {user.full_name},

We received a request to reset your password for your Learnogic account.

Click the link below to reset your password:
{reset_link}

This link will expire in 1 hour.

If you did not request a password reset, please ignore this email or contact us on  if you have concerns.

Best wishes
The Learnogic team
cultivating excellence""",
            body_html=f"""
            <!DOCTYPE html>
            <html>
                <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700&display=swap" rel="stylesheet">
                </head>
                <body style="margin: 0; padding: 0; font-family: 'Montserrat', Arial, sans-serif; background-color: #f5f5f5;">
                    <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f4f4f4; padding: 20px 0;">
                        <tr>
                            <td align="center">
                                <table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                                    <!-- Header with Logo -->
                                    <tr>
                                        <td style="padding: 30px 40px; background-color: #ffffff;">
                                            <table width="100%" cellpadding="0" cellspacing="0">
                                                <tr>
                                                    <td>
                                                        <img src="https://s3.ap-south-1.amazonaws.com/learnogic.com/static/logo.jpeg" alt="Learnogic Logo" style="height: 50px; display: block;">
                                                    </td>
                                                </tr>
                                            </table>
                                        </td>
                                    </tr>
                                    
                                    <!-- Main Content -->
                                    <tr>
                                        <td style="padding: 0 40px 40px 40px;">
                                            <p style="margin: 0 0 15px 0; font-size: 14px; color: #333333; line-height: 1.6;">Dear {user.full_name},</p>
                                            
                                            <p style="margin: 0 0 15px 0; font-size: 14px; color: #333333; line-height: 1.6;">We received a request to reset your password for your Learnogic account.</p>
                                            
                                            <p style="margin: 0 0 20px 0; font-size: 14px; color: #333333; line-height: 1.6;">Click the button below to reset your password:</p>
                                            
                                            <table cellpadding="0" cellspacing="0" style="margin: 0 0 20px 0;">
                                                <tr>
                                                    <td style="background-color: #007bff; border-radius: 5px; padding: 12px 30px;">
                                                        <a href="{reset_link}" style="color: #ffffff; text-decoration: none; font-weight: 600; font-size: 14px; display: inline-block;">Reset Password</a>
                                                    </td>
                                                </tr>
                                            </table>
                                            
                                            <p style="margin: 0 0 15px 0; font-size: 14px; color: #333333; line-height: 1.6;">Or copy and paste this link into your browser:</p>
                                            <p style="margin: 0 0 20px 0; font-size: 14px; color: #007bff; word-break: break-all;">{reset_link}</p>
                                            
                                            <p style="margin: 0 0 15px 0; font-size: 14px; color: #333333; line-height: 1.6;"><strong>This link will expire in 1 hour.</strong></p>
                                            
                                            <p style="margin: 0 0 15px 0; font-size: 14px; color: #333333; line-height: 1.6;">If you did not request a password reset, please ignore this email or contact us on support@learnogic.com if you have concerns.</p>
                                            <p style="margin: 0 0 15px 0; font-size: 14px; color: #333333; line-height: 1.6;">Please do not reply this email.</p>
                                            
                                            <p style="margin: 25px 0 0 0; font-size: 14px; color: #333333; line-height: 1.6;">Best wishes</p>
                                            <p style="margin: 5px 0 0 0; font-size: 14px; color: #333333; line-height: 1.2;">The Learnogic team<br>cultivating excellence</p>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                    </table>
                </body>
            </html>
            """,
            from_address="info@learnogic.com"
        )
        
        email_response = ses_service.send_email(reset_email)
        logger.info(f"Password reset email sent to {user.email}. MessageId: {email_response.message_id}")
        
    except Exception as email_error:
        logger.error(f"Failed to send password reset email to {user.email}: {str(email_error)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send password reset email. Please try again later."
        )
    
    return {
        "message": "Password reset instructions have been sent to your email address. Please check your inbox and follow the instructions to reset your password."
    }


@router.post("/password-reset")
def reset_password(
    reset_data: schemas.PasswordReset,
    db: Session = Depends(get_db)
):
    """Reset password using the token from email"""
    
    # Find the token
    token_record = db.query(models.PasswordResetToken).filter(
        models.PasswordResetToken.token == reset_data.token
    ).first()
    
    if not token_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token."
        )
    
    # Check if token is already used
    if token_record.used:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset token has already been used."
        )
    
    # Check if token is expired
    if datetime.utcnow() > token_record.expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset token has expired. Please request a new one."
        )
    
    # Get the user
    user = db.query(models.User).filter(models.User.id == token_record.user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found."
        )
    
    # Update user's password
    user.hashed_password = auth.get_password_hash(reset_data.new_password)
    
    # Mark token as used
    token_record.used = True
    
    db.commit()
    
    # Optional: Send confirmation email
    try:
        confirmation_email = EmailRequest(
            to_addresses=[user.email],
            subject="Password successfully reset",
            body_text=f"""Dear {user.full_name},

Your password has been successfully reset.

If you did not make this change, please contact us immediately.

Best wishes
The Learnogic team
cultivating excellence""",
            body_html=f"""
            <!DOCTYPE html>
            <html>
                <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700&display=swap" rel="stylesheet">
                </head>
                <body style="margin: 0; padding: 0; font-family: 'Montserrat', Arial, sans-serif; background-color: #f5f5f5;">
                    <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f4f4f4; padding: 20px 0;">
                        <tr>
                            <td align="center">
                                <table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                                    <tr>
                                        <td style="padding: 30px 40px; background-color: #ffffff;">
                                            <img src="https://s3.ap-south-1.amazonaws.com/learnogic.com/static/logo.jpeg" alt="Learnogic Logo" style="height: 50px; display: block;">
                                        </td>
                                    </tr>
                                    <tr>
                                        <td style="padding: 0 40px 40px 40px;">
                                            <p style="margin: 0 0 15px 0; font-size: 14px; color: #333333; line-height: 1.6;">Dear {user.full_name},</p>
                                            
                                            <p style="margin: 0 0 15px 0; font-size: 14px; color: #333333; line-height: 1.6;">Your password has been successfully reset.</p>
                                            
                                            <p style="margin: 0 0 15px 0; font-size: 14px; color: #333333; line-height: 1.6;">If you did not make this change, contact us immediately on support@learnogic.com.</p>
                                            <p style="margin: 0 0 15px 0; font-size: 14px; color: #333333; line-height: 1.6;">Please do not reply to this email.</p>
                                            
                                            <p style="margin: 25px 0 0 0; font-size: 14px; color: #333333; line-height: 1.6;">Best wishes</p>
                                            <p style="margin: 5px 0 0 0; font-size: 14px; color: #333333; line-height: 1.2;">The Learnogic team<br>cultivating excellence</p>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                    </table>
                </body>
            </html>
            """,
            from_address="info@learnogic.com"
        )
        
        ses_service.send_email(confirmation_email)
        
    except Exception as email_error:
        logger.error(f"Failed to send password reset confirmation email: {str(email_error)}")
    
    return {
        "message": "Password has been successfully reset. You can now log in with your new password."
    }


