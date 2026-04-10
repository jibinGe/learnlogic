from fastapi import APIRouter, Depends, HTTPException, status, Form, File, UploadFile, Body
from sqlalchemy.orm import Session
from typing import List, Optional
from .. import models, schemas, auth
from ..database import get_db
from ..utils.s3 import S3Client
import uuid
import json
import math
from ..config import settings
from datetime import datetime
from calendar import month_name

router = APIRouter(prefix="/event", tags=["Events"])

class EventS3Utils:
    ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/gif"]
    
    @staticmethod
    def generate_object_key(event_id: int, filename: str, category: str = "trainers") -> str:
        """Generate S3 object key for event files"""
        ext = filename.split('.')[-1]
        unique_filename = f"{uuid.uuid4()}.{ext}"
        return f"events/{event_id}/{category}/{unique_filename}"
    
    @staticmethod
    def get_file_category(content_type: str) -> str:
        """Determine file category based on content type"""
        if content_type in EventS3Utils.ALLOWED_IMAGE_TYPES:
            return "images"
        return "files"


def check_and_update_event_status(event: models.Event, db: Session) -> models.Event:
    """
    Check if event date has passed and update status to INACTIVE if needed.
    Only updates ACTIVE events - leaves ALL_SEATS_BOOKED unchanged.
    """
    # Skip if not ACTIVE or if required fields are missing
    if event.status != models.EventStatus.ACTIVE:
        return event
    
    if not event.date_year or not event.date_month or not event.date_day:
        return event
    
    try:
        # Parse the event date
        year = int(event.date_year)
        
        # Convert month name to number (e.g., "June" -> 6)
        month_names = {name.lower(): i for i, name in enumerate(month_name) if i > 0}
        month = month_names.get(event.date_month.lower())
        
        if not month:
            return event  # Invalid month name, skip
        
        # Handle date ranges like "3-28" - use the END date
        date_day_str = event.date_day.strip()
        if '-' in date_day_str:
            # Take the last date in the range
            day = int(date_day_str.split('-')[-1].strip())
        else:
            day = int(date_day_str)
        
        # Create event date
        event_date = datetime(year, month, day).date()
        today = datetime.now().date()
        
        # If event date has passed, mark as INACTIVE
        if event_date < today:
            event.status = models.EventStatus.INACTIVE
            db.commit()
            db.refresh(event)
            
    except (ValueError, AttributeError) as e:
        # If date parsing fails, just return the event unchanged
        print(f"Error parsing event date for event {event.id}: {str(e)}")
        pass
    
    return event


def check_and_update_all_events_status(events: List[models.Event], db: Session) -> List[models.Event]:
    """
    Check and update status for multiple events.
    """
    updated_events = []
    for event in events:
        updated_event = check_and_update_event_status(event, db)
        updated_events.append(updated_event)
    
    return updated_events


# Presigned URL endpoints for events
@router.post("/{event_id}/presigned-url", response_model=schemas.PresignedUrlResponse)
async def get_presigned_url_for_event(
    event_id: int,
    request: schemas.PresignedUrlRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Generate presigned URL for uploading files to an event"""
    if current_user.user_type != models.UserType.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to upload files"
        )
    
    # Verify event exists
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )
    
    try:
        s3_client = S3Client()
        
        # Generate object key
        object_key = EventS3Utils.generate_object_key(
            event_id, 
            request.filename, 
            request.subfolder or "trainers"
        )
        
        # Generate presigned URL
        presigned_data = s3_client.generate_presigned_url(
            object_key=object_key,
            content_type=request.content_type,
            max_file_size=request.max_file_size
        )
        
        return schemas.PresignedUrlResponse(**presigned_data)
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating presigned URL: {str(e)}"
        )

@router.post("/{event_id}/multipart-upload", response_model=schemas.MultipartUploadResponse)
async def initiate_multipart_upload_for_event(
    event_id: int,
    request: schemas.MultipartUploadRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Initiate multipart upload for large event files"""
    if current_user.user_type != models.UserType.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to upload files"
        )
    
    # Verify event exists
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )
    
    try:
        s3_client = S3Client()
        
        # Generate object key
        object_key = EventS3Utils.generate_object_key(
            event_id,
            request.filename,
            request.subfolder or "trainers"
        )
        
        # Initiate multipart upload
        upload_data = s3_client.initiate_multipart_upload(
            object_key=object_key,
            content_type=request.content_type
        )
        
        # Calculate part size and total parts
        part_size = 5 * 1024 * 1024  # 5MB
        total_parts = math.ceil(request.file_size / part_size)
        
        return schemas.MultipartUploadResponse(
            upload_id=upload_data["upload_id"],
            object_key=upload_data["object_key"],
            part_size=part_size,
            total_parts=total_parts
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error initiating multipart upload: {str(e)}"
        )

@router.post("/multipart-part-url", response_model=schemas.MultipartPartResponse)
async def get_multipart_part_url(
    request: schemas.MultipartPartRequest,
    current_user: models.User = Depends(auth.get_current_user)
):
    """Get presigned URL for uploading a specific part"""
    if current_user.user_type != models.UserType.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized"
        )
    
    try:
        s3_client = S3Client()
        
        presigned_url = s3_client.generate_presigned_url_for_part(
            object_key=request.object_key,
            upload_id=request.upload_id,
            part_number=request.part_number
        )
        
        return schemas.MultipartPartResponse(
            part_number=request.part_number,
            presigned_url=presigned_url
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating part URL: {str(e)}"
        )

@router.post("/complete-multipart", response_model=schemas.MultipartCompleteResponse)
async def complete_multipart_upload(
    request: schemas.MultipartCompleteRequest,
    current_user: models.User = Depends(auth.get_current_user)
):
    """Complete multipart upload"""
    if current_user.user_type != models.UserType.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized"
        )
    
    try:
        s3_client = S3Client()
        
        final_url = s3_client.complete_multipart_upload(
            object_key=request.object_key,
            upload_id=request.upload_id,
            parts=request.parts
        )
        
        return schemas.MultipartCompleteResponse(
            final_url=final_url,
            object_key=request.object_key
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error completing multipart upload: {str(e)}"
        )

@router.get("/admin", response_model=List[schemas.Event])
async def admin_get_events(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Get all events and auto-update expired events to INACTIVE"""
    if current_user.user_type != models.UserType.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update events"
        )
    try:
        # 1. Start the query
        query = db.query(models.Event)
        
        # 2. Add the filter for is_hidden = False
        # SQLAlchemy maps 'False' directly to the appropriate database boolean value
        # query = query.filter(models.Event.is_hidden == False)
        
        # 3. Add ordering and execute the query
        events = query.order_by(models.Event.id.asc()).all()
        
        # Check and update status for all events
        # Note: check_and_update_all_events_status will now only receive
        # events where is_hidden is False.
        events = check_and_update_all_events_status(events, db)
        
        return events
    except Exception as e:
        print(f"Error in get_events: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving events: {str(e)}"
        )
    
# Updated CRUD endpoints
@router.get("/", response_model=List[schemas.Event])
async def get_events(
    db: Session = Depends(get_db)
):
    """Get all events and auto-update expired events to INACTIVE"""
    try:
        # 1. Start the query
        query = db.query(models.Event)
        
        # 2. Add the filter for is_hidden = False
        # SQLAlchemy maps 'False' directly to the appropriate database boolean value
        query = query.filter(models.Event.is_hidden == False)
        
        # 3. Add ordering and execute the query
        events = query.order_by(models.Event.id.asc()).all()
        
        # Check and update status for all events
        # Note: check_and_update_all_events_status will now only receive
        # events where is_hidden is False.
        events = check_and_update_all_events_status(events, db)
        
        return events
    except Exception as e:
        print(f"Error in get_events: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving events: {str(e)}"
        )

@router.get("/{event_id}", response_model=schemas.Event)
async def get_event(
    event_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific event by ID and auto-update if expired"""
    try:
        event = db.query(models.Event).filter(models.Event.id == event_id).first()
        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event not found"
            )
        
        # Check and update status if needed
        event = check_and_update_event_status(event, db)
        
        return event
    except Exception as e:
        print(f"Error in get_event: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving event: {str(e)}"
        )
   
@router.get("/by-name/{event_id}/{event_name}", response_model=schemas.Event)
def read_theme_by_name(
    event_id: int,
    event_name: str,
    db: Session = Depends(get_db)
):
    # import re

    # def normalize_name(name: str) -> str:
    #     # Convert to lowercase and remove all non-alphanumeric characters
    #     name = name.strip().lower()
    #     name = re.sub(r'[^a-z0-9]', '', name)
    #     return name
    
    # Try exact match first
    event = db.query(models.Event).filter(
        models.Event.id == event_id
    ).first()
    
    # if not event:
    #     all_events = db.query(models.Event).all()
    #     normalized_input = normalize_name(event_id)
        
    #     for db_event in all_events:
    #         if normalize_name(db_event.title) == normalized_input:
    #             event = db_event
    #             break   # ✅ take the first match only
    
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event with name '{event_id}' not found"
        )
    
    # Check and update status if needed
    event = check_and_update_event_status(event, db)
    
    return event


@router.post("/", response_model=schemas.Event)
async def create_event(
    title: str = Form(...),
    date_month: str = Form(...),
    date_day: str = Form(None),
    date_year: str = Form(...),
    location: str = Form(...),
    price: str = Form(...),
    type: str = Form(...),
    time: str = Form(...),
    color: str = Form(...),
    teachers: List[str] = Form(...),
    qualification: Optional[str] = Form(None),
    exam_board: Optional[str] = Form(None),
    subject: Optional[str] = Form(None),
    why_attend: str = Form(...),  # JSON string
    programme: str = Form(...),  # JSON string
    trainer_data: Optional[str] = Form(None),  # JSON string, optional
    trainer_files: Optional[str] = Form(None),  # JSON string with file info, optional
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Create a new event with files uploaded via presigned URLs"""
    if current_user.user_type != models.UserType.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to create events"
        )

    try:
        # Parse JSON strings
        why_attend_dict = json.loads(why_attend)
        programme_dict = json.loads(programme)

        # Create event
        db_event = models.Event(
            title=title,
            date_month=date_month,
            date_day=date_day,
            date_year=date_year,
            location=location,
            price=price,
            time=time,
            type=type,
            color=color,
            teachers=teachers,
            why_attend=why_attend_dict,
            programme=programme_dict,
            trainers={"items": []},  # Default empty
            qualification=qualification,
            exam_board=exam_board,
            subject=subject
        )
        db.add(db_event)
        db.flush()

        # Process trainers ONLY if both trainer_data and trainer_files are provided
        if trainer_data and trainer_files:
            trainer_data_dict = json.loads(trainer_data)
            trainer_files_list = json.loads(trainer_files)
            trainers_with_photos = []
            
            # Match trainer data with uploaded files (similar to old API's zip logic)
            for trainer_info, file_info in zip(trainer_data_dict["items"], trainer_files_list):
                # Extract the final URL from S3 path
                final_url = f"https://{S3Client().bucket_name}.s3.{settings.AWS_REGION}.amazonaws.com/{file_info['object_key']}"
                
                # Combine trainer data with photo info
                trainer_with_photo = trainer_info.copy()  # Copy trainer data
                trainer_with_photo["photo"] = {
                    "url": final_url,
                    "file_type": file_info["content_type"],
                    "original_name": file_info["original_filename"],
                    "category": "images"
                }
                trainers_with_photos.append(trainer_with_photo)
            
            db_event.trainers = {"items": trainers_with_photos}
        
        # If only trainer_data is provided (no files), store trainer data without photos
        elif trainer_data and not trainer_files:
            trainer_data_dict = json.loads(trainer_data)
            db_event.trainers = {"items": trainer_data_dict["items"]}

        db.commit()
        db.refresh(db_event)
        return db_event

    except Exception as e:
        print(f"Error in create_event: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating event: {str(e)}"
        )


@router.put("/{event_id}", response_model=schemas.Event)
async def update_event(
    event_id: int,
    title: Optional[str] = Form(None),
    date_month: Optional[str] = Form(None),
    date_day: Optional[str] = Form(None),
    date_year: Optional[str] = Form(None),
    location: Optional[str] = Form(None),
    price: Optional[str] = Form(None),
    type: Optional[str] = Form(None),
    time: Optional[str] = Form(None),
    color: Optional[str] = Form(None),
    teachers: Optional[List[str]] = Form(None),
    qualification: Optional[str] = Form(None),
    exam_board: Optional[str] = Form(None),
    subject: Optional[str] = Form(None),
    why_attend: Optional[str] = Form(None),  # JSON string
    programme: Optional[str] = Form(None),  # JSON string
    trainer_data: Optional[str] = Form(None),  # JSON string, optional
    trainer_files: Optional[str] = Form(None),  # JSON string with file info, optional
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Update an event with files uploaded via presigned URLs"""
    if current_user.user_type != models.UserType.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update events"
        )

    try:
        event = db.query(models.Event).filter(models.Event.id == event_id).first()
        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event not found"
            )

        # Update basic event fields
        if title is not None:
            event.title = title
        if date_month is not None:
            event.date_month = date_month
        if date_day is not None:
            event.date_day = date_day
        if date_year is not None:
            event.date_year = date_year
        if location is not None:
            event.location = location
        if price is not None:
            event.price = price
        if type is not None:
            event.type = type
        if time is not None:
            event.time = time
        if color is not None:
            event.color = color
        if teachers is not None:
            event.teachers = teachers
        if qualification is not None:
            event.qualification = qualification
        if exam_board is not None:
            event.exam_board = exam_board
        if subject is not None:
            event.subject = subject
        if why_attend is not None:
            event.why_attend = json.loads(why_attend)
        if programme is not None:
            event.programme = json.loads(programme)

        # Handle trainer updates with the same logic as create event
        if trainer_data and trainer_files:
            # Delete old trainer photos from S3 if they exist
            if event.trainers and "items" in event.trainers:
                s3_client = S3Client()
                for trainer in event.trainers["items"]:
                    if "photo" in trainer and trainer["photo"] is not None and "url" in trainer["photo"]:
                        # Extract object key from URL
                        url_parts = trainer["photo"]["url"].split("/")
                        if len(url_parts) >= 3:
                            object_key = "/".join(url_parts[-3:])  # events/{id}/trainers/{filename}
                            s3_client.delete_object(object_key)

            # Process new trainers with photos (matching trainer data with files)
            trainer_data_dict = json.loads(trainer_data)
            trainer_files_list = json.loads(trainer_files)
            trainers_with_photos = []
            
            for trainer_info, file_info in zip(trainer_data_dict["items"], trainer_files_list):
                # Extract the final URL from S3 path
                final_url = f"https://{S3Client().bucket_name}.s3.{settings.AWS_REGION}.amazonaws.com/{file_info['object_key']}"
                
                # Combine trainer data with photo info
                trainer_with_photo = trainer_info.copy()  # Copy trainer data
                trainer_with_photo["photo"] = {
                    "url": final_url,
                    "file_type": file_info["content_type"],
                    "original_name": file_info["original_filename"],
                    "category": "images"
                }
                trainers_with_photos.append(trainer_with_photo)
            
            event.trainers = {"items": trainers_with_photos}

        # If only trainer_data is provided (no files), update trainer data without photos
        elif trainer_data and not trainer_files:
            # Delete old trainer photos from S3 since we're updating to no photos
            if event.trainers and "items" in event.trainers:
                s3_client = S3Client()
                for trainer in event.trainers["items"]:
                    if "photo" in trainer and trainer["photo"] is not None and "url" in trainer["photo"]:
                        # Extract object key from URL
                        url_parts = trainer["photo"]["url"].split("/")
                        if len(url_parts) >= 3:
                            object_key = "/".join(url_parts[-3:])  # events/{id}/trainers/{filename}
                            s3_client.delete_object(object_key)
            
            # Store trainer data without photos
            trainer_data_dict = json.loads(trainer_data)
            event.trainers = {"items": trainer_data_dict["items"]}

        # If only trainer_files are provided (no trainer_data), create photo-only trainers
        elif not trainer_data and trainer_files:
            # Delete old trainer photos first
            if event.trainers and "items" in event.trainers:
                s3_client = S3Client()
                for trainer in event.trainers["items"]:
                    if "photo" in trainer and trainer["photo"] is not None and "url" in trainer["photo"]:
                        url_parts = trainer["photo"]["url"].split("/")
                        if len(url_parts) >= 3:
                            object_key = "/".join(url_parts[-3:])
                            s3_client.delete_object(object_key)

            trainer_files_list = json.loads(trainer_files)
            trainers_with_photos = []
            for file_info in trainer_files_list:
                final_url = f"https://{S3Client().bucket_name}.s3.{settings.AWS_REGION}.amazonaws.com/{file_info['object_key']}"
                
                trainer_data = {
                    "photo": {
                        "url": final_url,
                        "file_type": file_info["content_type"],
                        "original_name": file_info["original_filename"],
                        "category": "images"
                    }
                }
                trainers_with_photos.append(trainer_data)
            
            event.trainers = {"items": trainers_with_photos}

        # If neither trainer_data nor trainer_files are provided, keep existing trainers unchanged

        db.commit()
        db.refresh(event)
        return event

    except Exception as e:
        print(f"Error in update_event: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating event: {str(e)}"
        )
    
@router.delete("/{event_id}")
async def delete_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Delete an event and associated files"""
    if current_user.user_type != models.UserType.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete events"
        )

    try:
        event = db.query(models.Event).filter(models.Event.id == event_id).first()
        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event not found"
            )

        # Delete trainer photos from S3 if they exist
        if event.trainers is not None and isinstance(event.trainers, dict) and "items" in event.trainers:
            s3_client = S3Client()
            for trainer in event.trainers["items"]:
                if isinstance(trainer, dict) and "photo" in trainer and isinstance(trainer["photo"], dict) and "url" in trainer["photo"]:
                    # Extract object key from URL
                    url_parts = trainer["photo"]["url"].split("/")
                    if len(url_parts) >= 3:
                        object_key = "/".join(url_parts[-3:])  # events/{id}/trainers/{filename}
                        s3_client.delete_object(object_key)

        # Delete event from database
        db.delete(event)
        db.commit()
        return {"message": "Event and associated files deleted successfully"}

    except Exception as e:
        print(f"Error in delete_event: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting event: {str(e)}"
        )
    
@router.patch("/{event_id}/admin-update", response_model=schemas.Event)
def admin_update_event_fields(
    event_id: int,
    update_data: schemas.EventUpdateAdmin,
    db: Session = Depends(get_db),
    current_user = Depends(auth.get_current_user)
):
    if current_user.user_type != models.UserType.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized"
        )
    
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    if update_data.status:
        event.status = update_data.status
    if update_data.status is not None:
        event.status = update_data.status
    if update_data.is_hidden is not None:
        event.is_hidden = update_data.is_hidden
    if update_data.total_seats is not None:
        if update_data.total_seats < event.seats_booked:
            raise HTTPException(status_code=400, detail="Total seats cannot be less than already booked seats.")
        event.total_seats = update_data.total_seats

    db.commit()
    db.refresh(event)
    return event



