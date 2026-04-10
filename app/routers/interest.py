# routes/interests.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional, Dict, Any
from .. import models, schemas, auth
from ..database import get_db

router = APIRouter(prefix="/interests", tags=["Interests"])

@router.post("/", response_model=schemas.Interest, status_code=status.HTTP_201_CREATED)
def create_interest(
    interest_data: schemas.InterestCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Create a new interest entry for the current user"""
    try:
        # Validate that the interest_id exists in the corresponding table
        if interest_data.item_type == "event":
            event_exists = db.query(models.Event).filter(models.Event.id == interest_data.interest_id).first()
            if not event_exists:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Event not found"
                )
        elif interest_data.item_type == "resource":
            resource_exists = db.query(models.Resources).filter(models.Resources.id == interest_data.interest_id).first()
            if not resource_exists:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Resource not found"
                )
        
        # Check if interest already exists for this user
        existing_interest = db.query(models.Interest).filter(
            models.Interest.user_id == current_user.id,
            models.Interest.interest_id == interest_data.interest_id,
            models.Interest.item_type == interest_data.item_type
        ).first()
        
        if existing_interest:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Interest already exists for this item"
            )
        
        # Create new interest instance using the current user's ID
        db_interest = models.Interest(
            interest_id=interest_data.interest_id,
            item_type=interest_data.item_type,
            user_id=current_user.id  # Get user_id from token
        )
        
        # Add to database
        db.add(db_interest)
        db.commit()
        db.refresh(db_interest)
        
        return db_interest
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating interest: {str(e)}"
        )

@router.get("/", response_model=List[schemas.InterestWithDetails])
def get_user_interests(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Get all interests for the current user with full details"""
    interests = db.query(models.Interest).filter(
        models.Interest.user_id == current_user.id
    ).all()
    
    result = []
    for interest in interests:
        # Get user details
        user = db.query(models.User).filter(models.User.id == interest.user_id).first()
        user_details = None
        if user:
            user_details = {
                "id": user.id,
                "email": user.email,
                "title": user.title,
                "full_name": user.full_name,
                "job_title": user.job_title,
                "school": user.school,
                "billing_address": user.billing_address,
                "user_type": user.user_type,
                "is_active": user.is_active
            }
        
        interest_data = {
            "id": interest.id,
            "interest_id": interest.interest_id,
            "item_type": interest.item_type,
            "user_id": interest.user_id,
            "user_details": user_details,
            "details": None
        }
        
        # Fetch details based on item_type
        if interest.item_type == "event":
            event = db.query(models.Event).filter(models.Event.id == interest.interest_id).first()
            if event:
                interest_data["details"] = {
                    "id": event.id,
                    "title": event.title,
                    "date_month": event.date_month,
                    "date_day": event.date_day,
                    "date_year": event.date_year,
                    "location": event.location,
                    "price": event.price,
                    "type": event.type,
                    "time": event.time,
                    "color": event.color,
                    "teachers": event.teachers,
                    "why_attend": event.why_attend,
                    "programme": event.programme,
                    "trainers": event.trainers,
                    "qualification": event.qualification,
                    "exam_board": event.exam_board,
                    "subject": event.subject,
                    "total_seats": event.total_seats,
                    "seats_booked": event.seats_booked,
                    "status": event.status,
                    "created_at": event.created_at,
                    "updated_at": event.updated_at
                }
        
        elif interest.item_type == "resource":
            resource = db.query(models.Resources).filter(models.Resources.id == interest.interest_id).first()
            if resource:
                interest_data["details"] = {
                    "id": resource.id,
                    "name": resource.name,
                    "data": resource.data,
                    "created_at": resource.created_at,
                    "updated_at": resource.updated_at
                }
        
        result.append(interest_data)
    
    return result

@router.get("/all", response_model=schemas.PaginatedResponse[schemas.InterestWithDetails])
def get_all_interests(
    page: int = Query(1, gt=0),
    page_size: int = Query(10, gt=0, le=100),
    item_type: Optional[str] = Query(None, description="Filter by item_type: event, resource, or others"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Get all interests with pagination and full details (Admin access recommended)"""
    
    # Calculate offset
    offset = (page - 1) * page_size
    
    # Build query with optional filter
    query = db.query(models.Interest)
    if item_type:
        query = query.filter(models.Interest.item_type == item_type)
    
    # Get total count
    total_count = query.count()
    
    # Get interests for current page
    interests = query.order_by(models.Interest.id.desc()).offset(offset).limit(page_size).all()
    
    # Calculate total pages
    total_pages = -(-total_count // page_size)  # Ceiling division
    
    result = []
    for interest in interests:
        # Get user details
        user = db.query(models.User).filter(models.User.id == interest.user_id).first()
        user_details = None
        if user:
            user_details = {
                "id": user.id,
                "email": user.email,
                "title": user.title,
                "full_name": user.full_name,
                "job_title": user.job_title,
                "school": user.school,
                "billing_address": user.billing_address,
                "user_type": user.user_type,
                "is_active": user.is_active
            }
        
        interest_data = {
            "id": interest.id,
            "interest_id": interest.interest_id,
            "item_type": interest.item_type,
            "user_id": interest.user_id,
            "user_details": user_details,
            "details": None
        }
        
        # Fetch details based on item_type
        if interest.item_type == "event":
            event = db.query(models.Event).filter(models.Event.id == interest.interest_id).first()
            if event:
                interest_data["details"] = {
                    "id": event.id,
                    "title": event.title,
                    "date_month": event.date_month,
                    "date_day": event.date_day,
                    "date_year": event.date_year,
                    "location": event.location,
                    "price": event.price,
                    "type": event.type,
                    "time": event.time,
                    "color": event.color,
                    "teachers": event.teachers,
                    "why_attend": event.why_attend,
                    "programme": event.programme,
                    "trainers": event.trainers,
                    "qualification": event.qualification,
                    "exam_board": event.exam_board,
                    "subject": event.subject,
                    "total_seats": event.total_seats,
                    "seats_booked": event.seats_booked,
                    "status": event.status,
                    "created_at": event.created_at,
                    "updated_at": event.updated_at
                }
        
        elif interest.item_type == "resource":
            resource = db.query(models.Resources).filter(models.Resources.id == interest.interest_id).first()
            if resource:
                interest_data["details"] = {
                    "id": resource.id,
                    "name": resource.name,
                    "data": resource.data,
                    "created_at": resource.created_at,
                    "updated_at": resource.updated_at
                }
        
        result.append(interest_data)
    
    return {
        "items": result,
        "total": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages
    }