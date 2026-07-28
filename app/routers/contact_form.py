from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import logging

# Import your modules (adjust paths as needed)
from ..database import get_db
from ..models import ContactForm
from ..schemas import ContactFormCreate, ContactFormUpdate, ContactForm as ContactFormSchema
from ..utils.ses import SESService
from ..schemas import EmailRequest, EmailResponse

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/contact-forms",
    tags=["Contact Forms"]
)
ses_service = SESService()


def get_recipient_email(position: str) -> str:
    """Determine recipient email based on position"""
    position_lower = position.lower()
    
    if "examiner" in position_lower:
        return "careers@learnogic.com"
    elif "teacher" in position_lower:
        return "support@learnogic.com"
    else:
        # Default email for other positions
        return "info@learnogic.com"


@router.post("/", response_model=ContactFormSchema, status_code=status.HTTP_201_CREATED)
def create_contact_form(
    form_data: ContactFormCreate,
    db: Session = Depends(get_db)
):
    """
    Submit a new contact form.
    Sends email notification to appropriate department based on position.
    """
    # Create new contact form entry
    db_contact_form = ContactForm(
        name=form_data.name,
        email=form_data.email,
        school_name=form_data.school_name,
        position=form_data.position,
        message=form_data.message
    )
    
    db.add(db_contact_form)
    db.commit()
    db.refresh(db_contact_form)
    
    # Determine recipient email based on position
    recipient_email = get_recipient_email(form_data.position)
    
    # Send notification email to appropriate department
    try:
        notification_email = EmailRequest(
            to_addresses=[recipient_email],
            subject=f"New Contact Form Submission - {form_data.position}",
            body_text=f"""New Contact Form Submission

Name: {form_data.name}
Email: {form_data.email}
School/Institution: {form_data.school_name}
Position: {form_data.position}

Message:
{form_data.message if form_data.message else 'No message provided'}

---
Submission ID: {db_contact_form.id}
Submitted at: {db_contact_form.created_at}
""",
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
                                                        <img src="https://learnogic.s3.ap-south-1.amazonaws.com/static/logo.jpeg" alt="Learnogic Logo" style="height: 50px; display: block;">
                                                    </td>
                                                </tr>
                                            </table>
                                        </td>
                                    </tr>
                                    
                                    <!-- Main Content -->
                                    <tr>
                                        <td style="padding: 0 40px 40px 40px;">
                                            <h2 style="margin: 0 0 20px 0; font-size: 20px; color: #333333; font-weight: 600;">New Contact Form Submission</h2>
                                            
                                            <table width="100%" cellpadding="8" cellspacing="0" style="border-collapse: collapse;">
                                                <tr>
                                                    <td style="padding: 10px; background-color: #f8f8f8; border: 1px solid #e0e0e0; font-weight: 600; width: 30%;">Name:</td>
                                                    <td style="padding: 10px; border: 1px solid #e0e0e0;">{form_data.name}</td>
                                                </tr>
                                                <tr>
                                                    <td style="padding: 10px; background-color: #f8f8f8; border: 1px solid #e0e0e0; font-weight: 600;">Email:</td>
                                                    <td style="padding: 10px; border: 1px solid #e0e0e0;"><a href="mailto:{form_data.email}" style="color: #0066cc;">{form_data.email}</a></td>
                                                </tr>
                                                <tr>
                                                    <td style="padding: 10px; background-color: #f8f8f8; border: 1px solid #e0e0e0; font-weight: 600;">School/Institution:</td>
                                                    <td style="padding: 10px; border: 1px solid #e0e0e0;">{form_data.school_name}</td>
                                                </tr>
                                                <tr>
                                                    <td style="padding: 10px; background-color: #f8f8f8; border: 1px solid #e0e0e0; font-weight: 600;">Position:</td>
                                                    <td style="padding: 10px; border: 1px solid #e0e0e0;">{form_data.position}</td>
                                                </tr>
                                            </table>
                                            
                                            <h3 style="margin: 25px 0 10px 0; font-size: 16px; color: #333333; font-weight: 600;">Message:</h3>
                                            <div style="padding: 15px; background-color: #f8f8f8; border-left: 4px solid #ccaa55; border-radius: 4px; font-size: 14px; color: #333333; line-height: 1.6;">
                                                {form_data.message if form_data.message else '<em>No message provided</em>'}
                                            </div>
                                            
                                            <p style="margin: 25px 0 0 0; font-size: 12px; color: #666666;">
                                                <strong>Submission ID:</strong> {db_contact_form.id}<br>
                                                <strong>Submitted at:</strong> {db_contact_form.created_at}
                                            </p>
                                        </td>
                                    </tr>
                                    
                                    <!-- Footer -->
                                    <tr>
                                        <td style="padding: 20px 40px; background-color: #f8f8f8; text-align: center;">
                                            <p style="margin: 0; font-size: 12px; color: #666666;">
                                                This is an automated notification from Learnogic contact form system.
                                            </p>
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
        
        email_response = ses_service.send_email(notification_email)
        logger.info(f"Contact form notification sent to {recipient_email}. MessageId: {email_response.message_id}")
        
    except Exception as email_error:
        logger.error(f"Failed to send contact form notification: {str(email_error)}")
        # Don't fail the request if email fails
    
    # Send confirmation email to the submitter
    try:
        confirmation_email = EmailRequest(
            to_addresses=[form_data.email],
            subject="Message submitted",
            body_text=f"""Dear {form_data.name},

Thank you for reaching out to us. We have received your message and will get back to you shortly.

We appreciate your interest in Learnogic.

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
                                                        <img src="https://learnogic.s3.ap-south-1.amazonaws.com/static/logo.jpeg" alt="Learnogic Logo" style="height: 50px; display: block;">
                                                    </td>
                                                </tr>
                                            </table>
                                        </td>
                                    </tr>
                                    
                                    <!-- Main Content -->
                                    <tr>
                                        <td style="padding: 0 40px 40px 40px;">
                                            <p style="margin: 0 0 15px 0; font-size: 14px; color: #333333; line-height: 1.6;">Dear {form_data.name},</p>
                                            
                                            <p style="margin: 0 0 15px 0; font-size: 14px; color: #333333; line-height: 1.6;">Thank you for contacting us.</p>
                                            <p style="margin: 0 0 15px 0; font-size: 14px; color: #333333; line-height: 1.6;">We’ve received your message and will be in touch with you shortly.</p>
                                            
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
        
        email_response = ses_service.send_email(confirmation_email)
        logger.info(f"Confirmation email sent to {form_data.email}. MessageId: {email_response.message_id}")
        
    except Exception as email_error:
        logger.error(f"Failed to send confirmation email to {form_data.email}: {str(email_error)}")
    
    return db_contact_form


@router.get("/", response_model=List[ContactFormSchema])
def get_all_contact_forms(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """
    Retrieve all contact form submissions with pagination.
    """
    contact_forms = db.query(ContactForm).order_by(ContactForm.created_at.desc()).offset(skip).limit(limit).all()
    return contact_forms


@router.get("/{form_id}", response_model=ContactFormSchema)
def get_contact_form(
    form_id: int,
    db: Session = Depends(get_db)
):
    """
    Retrieve a specific contact form submission by ID.
    """
    contact_form = db.query(ContactForm).filter(ContactForm.id == form_id).first()
    
    if not contact_form:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Contact form with ID {form_id} not found"
        )
    
    return contact_form


@router.put("/{form_id}", response_model=ContactFormSchema)
def update_contact_form(
    form_id: int,
    form_update: ContactFormUpdate,
    db: Session = Depends(get_db)
):
    """
    Update an existing contact form submission.
    """
    contact_form = db.query(ContactForm).filter(ContactForm.id == form_id).first()
    
    if not contact_form:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Contact form with ID {form_id} not found"
        )
    
    # Update only provided fields
    update_data = form_update.model_dump(exclude_unset=True)
    
    for field, value in update_data.items():
        setattr(contact_form, field, value)
    
    db.commit()
    db.refresh(contact_form)
    
    return contact_form


@router.delete("/{form_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contact_form(
    form_id: int,
    db: Session = Depends(get_db)
):
    """
    Delete a contact form submission.
    """
    contact_form = db.query(ContactForm).filter(ContactForm.id == form_id).first()
    
    if not contact_form:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Contact form with ID {form_id} not found"
        )
    
    db.delete(contact_form)
    db.commit()
    
    return None