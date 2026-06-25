from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
import math
from .. import models, schemas, auth
from ..database import get_db
from ..utils.ses import SESService
from ..schemas import EmailRequest
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/tutors",
    tags=["tutors"],
)

ses_service = SESService()

@router.post("/register", status_code=status.HTTP_201_CREATED)
def register_tutor(tutor: schemas.TutorRegister, db: Session = Depends(get_db)):
    # Check if user already exists
    db_user = db.query(models.User).filter(models.User.email == tutor.email).first()
    if db_user:
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )

    # Create new User
    hashed_password = auth.get_password_hash(tutor.password)
    new_user = models.User(
        email=tutor.email,
        hashed_password=hashed_password,
        full_name=tutor.firstName + " " + tutor.lastName,
        user_type=models.UserType.TUTOR,
        is_active=True
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Create TutorProfile
    new_profile = models.TutorProfile(
        user_id=new_user.id,
        mobile_number=tutor.mobileNumber,
        country=tutor.country,
        city=tutor.city,
        subjects=tutor.subjects,
        exam_boards=tutor.examBoards,
        qualifications=tutor.qualifications,
        languages=tutor.languages,
        teaching_method=tutor.teachingMethod,
        years_of_experience=tutor.yearsOfExperience,
        price_per_hour=tutor.pricePerHour,
        about_me=tutor.aboutMe,
        avatar_url=tutor.avatarUrl
    )
    db.add(new_profile)
    db.commit()

    # Send welcome email to the new tutor
    try:
        full_name = tutor.firstName + " " + tutor.lastName
        welcome_email = EmailRequest(
            to_addresses=[tutor.email],
            subject="Welcome - Registration successful",
            body_text=f"""Dear {full_name},

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
                                                        <img src="https://s3.ap-south-1.amazonaws.com/learnogic.com/static/logo.jpeg" alt="Learnogic Logo" style="height: 50px; display: block;">
                                                    </td>
                                                </tr>
                                            </table>
                                        </td>
                                    </tr>
                                    
                                    <!-- Main Content -->
                                    <tr>
                                        <td style="padding: 0 40px 40px 40px;">
                                            <p style="margin: 0 0 15px 0; font-size: 14px; color: #333333; line-height: 1.6;">Dear {full_name},</p>
                                            
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
            from_address="info@learnogic.com"
        )
        
        email_response = ses_service.send_email(welcome_email)
        logger.info(f"Welcome email sent to tutor {tutor.email}. MessageId: {email_response.message_id}")
        
    except Exception as email_error:
        logger.error(f"Failed to send welcome email to tutor {tutor.email}: {str(email_error)}")

    return {"message": "Tutor registered successfully"}

@router.get("/me", response_model=schemas.TutorProfileResponse)
def get_tutor_profile(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if current_user.user_type != models.UserType.TUTOR:
        raise HTTPException(status_code=403, detail="Not a tutor")
        
    profile = db.query(models.TutorProfile).filter(models.TutorProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Tutor profile not found")
        
    response = schemas.TutorProfileResponse(
        id=profile.id,
        user_id=profile.user_id,
        full_name=current_user.full_name,
        email=current_user.email,
        mobile_number=profile.mobile_number,
        country=profile.country,
        city=profile.city,
        subjects=profile.subjects,
        exam_boards=profile.exam_boards,
        qualifications=profile.qualifications,
        languages=profile.languages,
        teaching_method=profile.teaching_method,
        years_of_experience=profile.years_of_experience,
        price_per_hour=profile.price_per_hour,
        about_me=profile.about_me,
        avatar_url=profile.avatar_url,
        is_subscribed=profile.is_subscribed,
        created_at=profile.created_at
    )
    return response

@router.put("/me", response_model=schemas.TutorProfileResponse)
def update_tutor_profile(
    profile_update: schemas.TutorProfileUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if current_user.user_type != models.UserType.TUTOR:
        raise HTTPException(status_code=403, detail="Not a tutor")
        
    profile = db.query(models.TutorProfile).filter(models.TutorProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Tutor profile not found")

    update_data = profile_update.dict(exclude_unset=True)
    
    # Map from camelCase to snake_case for db model
    field_mapping = {
        "mobileNumber": "mobile_number",
        "examBoards": "exam_boards",
        "teachingMethod": "teaching_method",
        "yearsOfExperience": "years_of_experience",
        "pricePerHour": "price_per_hour",
        "aboutMe": "about_me",
        "avatarUrl": "avatar_url",
        "isSubscribed": "is_subscribed"
    }
    
    for key, value in update_data.items():
        db_field = field_mapping.get(key, key)
        setattr(profile, db_field, value)
        
    # Also update full_name if present in update?
    # TutorProfileUpdate doesn't have first/lastName right now. 
    # Can leave out user update for now, or just handle profile fields.

    db.commit()
    db.refresh(profile)
    
    return get_tutor_profile(db=db, current_user=current_user)

@router.get("/", response_model=schemas.PaginatedTutorResponse)
def list_tutors(
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db)
):
    query = db.query(models.TutorProfile).join(models.User)
    
    total = query.count()
    profiles = query.offset((page - 1) * page_size).limit(page_size).all()
    
    items = []
    for p in profiles:
        items.append(schemas.TutorProfileResponse(
            id=p.id,
            user_id=p.user_id,
            full_name=p.user.full_name,
            email=p.user.email,
            mobile_number=p.mobile_number,
            country=p.country,
            city=p.city,
            subjects=p.subjects,
            exam_boards=p.exam_boards,
            qualifications=p.qualifications,
            languages=p.languages,
            teaching_method=p.teaching_method,
            years_of_experience=p.years_of_experience,
            price_per_hour=p.price_per_hour,
            about_me=p.about_me,
            avatar_url=p.avatar_url,
            is_subscribed=p.is_subscribed,
            created_at=p.created_at
        ))
        
    return schemas.PaginatedTutorResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if page_size else 0
    )
