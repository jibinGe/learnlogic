from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from .. import models, schemas, auth
from ..database import get_db
from ..utils.ses import SESService
from ..schemas import EmailRequest, EmailResponse
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["Users"])
ses_service = SESService()

@router.post("/", response_model=schemas.User)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    user.email = user.email.lower().strip()
    # Check if user with same email already exists
    existing_user = db.query(models.User).filter(models.User.email == user.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email address already registered.",
        )

    # Create new user
    db_user = models.User(
        email=user.email,
        hashed_password=auth.get_password_hash(user.password),
        full_name=user.full_name,
        user_type=user.user_type,
        school=user.school,
        title=user.title,
        job_title=user.job_title
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    # Send welcome email to the new user
    try:
        # Prepare welcome email content
        welcome_email = EmailRequest(
            to_addresses=[user.email],
            subject="Welcome - Registration successful",
            body_text=f"""Dear {user.full_name},

Thank you for registering with us.

To get started, log in to your account and explore the various teacher CPDs, student events and resources we offer. Keep track of all your orders on your dashboard.

For any further information, please do not hesitate to contact us.

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
                                            <p style="margin: 0 0 15px 0; font-size: 14px; color: #333333; line-height: 1.6;">Dear {user.full_name},</p>
                                            
                                            <p style="margin: 0 0 15px 0; font-size: 14px; color: #333333; line-height: 1.6;">Thank you for registering with us.</p>
                                            
                                            <p style="margin: 0 0 15px 0; font-size: 14px; color: #333333; line-height: 1.6;">To get started, log in to your account and explore the various teacher CPDs, student events and resources we offer.</p>
                                            <p style="margin: 0 0 15px 0; font-size: 14px; color: #333333; line-height: 1.6;">Keep track of all your orders on your dashboard.</p>
                                            
                                            <p style="margin: 0 0 15px 0; font-size: 14px; color: #333333; line-height: 1.6;">For any further information, please do not hesitate to contact us.</p>
                                            
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
            from_address="info@learnogic.com"  # Your verified sender email
        )
        
        # Send the welcome email
        email_response = ses_service.send_email(welcome_email)
        logger.info(f"Welcome email sent to {user.email}. MessageId: {email_response.message_id}")
        
    except Exception as email_error:
        # Log the email error but don't fail user creation
        logger.error(f"Failed to send welcome email to {user.email}: {str(email_error)}")
        # Optionally, you could store this in a queue for retry later
    
    return db_user

@router.get("/me", response_model=schemas.User)
def read_user_me(db: Session = Depends(get_db),
                current_user: models.User = Depends(auth.get_current_user)):
    """
    Get current user's own information
    """
    return current_user

@router.get("/", response_model=List[schemas.User])
def read_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db),
               current_user: models.User = Depends(auth.get_current_user)):
    if current_user.user_type not in [models.UserType.ADMIN, models.UserType.TEACHER]:
        raise HTTPException(status_code=403, detail="Not authorized")
    users = db.query(models.User).offset(skip).limit(limit).all()
    return users

@router.put("/{user_id}", response_model=schemas.User)
def update_user(user_id: int, user: schemas.UserCreate, db: Session = Depends(get_db),
                current_user: models.User = Depends(auth.get_current_user)):
    if current_user.user_type not in [models.UserType.ADMIN, models.UserType.TEACHER]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    
    for field, value in user.dict(exclude_unset=True).items():
        if field == "password":
            setattr(db_user, "hashed_password", auth.get_password_hash(value))
        else:
            setattr(db_user, field, value)
    
    db.commit()
    db.refresh(db_user)
    return db_user

@router.delete("/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db),
                current_user: models.User = Depends(auth.get_current_user)):
    if current_user.user_type != models.UserType.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Delete dependent records safely via ORM to handle cascades
    if db_user.user_type == models.UserType.TUTOR:
        tutor_profile = db.query(models.TutorProfile).filter(models.TutorProfile.user_id == user_id).first()
        if tutor_profile:
            db.delete(tutor_profile)
            
    # Delete user's cart
    cart = db.query(models.Cart).filter(models.Cart.user_id == user_id).first()
    if cart:
        db.delete(cart)
        
    # Delete user's purchases
    purchases = db.query(models.Purchase).filter(models.Purchase.user_id == user_id).all()
    for purchase in purchases:
        db.delete(purchase)
        
    # Delete other simple dependent records
    db.query(models.Testimonial).filter(models.Testimonial.user_id == user_id).delete(synchronize_session=False)
    db.query(models.Interest).filter(models.Interest.user_id == user_id).delete(synchronize_session=False)
    db.query(models.PasswordResetToken).filter(models.PasswordResetToken.user_id == user_id).delete(synchronize_session=False)

    db.delete(db_user)
    db.commit()
    return {"detail": "User deleted"}
