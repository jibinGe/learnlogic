# routes/testimonials.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from .. import models, schemas, auth
from ..database import get_db
from ..utils.s3 import S3Client
import uuid
import re
from ..config import settings

router = APIRouter(prefix="/testimonials", tags=["Testimonials"])

class TestimonialS3Utils:
    ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/gif"]
    
    @staticmethod
    def generate_object_key(filename: str) -> str:
        """Generate S3 object key for testimonial images"""
        ext = filename.split('.')[-1]
        unique_filename = f"{uuid.uuid4()}.{ext}"
        return f"testimonials/{unique_filename}"
    
    @staticmethod
    def get_image_key_from_url(url: str) -> Optional[str]:
        """Extract the S3 key from the URL"""
        match = re.search(r'testimonials/.*$', url)
        return match.group(0) if match else None

    @staticmethod
    def delete_s3_image(s3_client: S3Client, image_url: str):
        """Delete image from S3"""
        if not image_url:
            return
            
        key = TestimonialS3Utils.get_image_key_from_url(image_url)
        if key:
            try:
                s3_client.delete_object(key)
            except Exception as e:
                print(f"Error deleting S3 object: {e}")

# Presigned URL endpoint for testimonials
@router.post("/presigned-url", response_model=schemas.PresignedUrlResponse)
async def get_presigned_url_for_testimonial(
    request: schemas.PresignedUrlRequest,
    current_user: models.User = Depends(auth.get_current_user)
):
    """Generate presigned URL for uploading testimonial images"""
    if current_user.user_type not in [models.UserType.ADMIN, models.UserType.TEACHER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to upload testimonial images"
        )
    
    # Validate that it's an image
    if request.content_type not in TestimonialS3Utils.ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only image files are allowed for testimonials"
        )
    
    try:
        s3_client = S3Client()
        
        # Generate object key
        object_key = TestimonialS3Utils.generate_object_key(request.filename)
        
        # Generate presigned URL with 50MB limit for images
        presigned_data = s3_client.generate_presigned_url(
            object_key=object_key,
            content_type=request.content_type,
            max_file_size=50 * 1024 * 1024  # 50MB max for images
        )
        
        return schemas.PresignedUrlResponse(**presigned_data)
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating presigned URL: {str(e)}"
        )

@router.post("/", response_model=schemas.Testimonial)
async def create_testimonial(
    testimonial_data: schemas.TestimonialCreateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Create a new testimonial with image uploaded via presigned URL"""
    
    if current_user.user_type not in [models.UserType.ADMIN, models.UserType.TEACHER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to create testimonials"
        )
    
    try:
        # Generate final URL from object key
        s3_client = S3Client()
        final_url = f"https://{s3_client.bucket_name}.s3.{settings.AWS_REGION}.amazonaws.com/{testimonial_data.picture_file.object_key}"
        
        db_testimonial = models.Testimonial(
            name=testimonial_data.name,
            stars=testimonial_data.stars,
            matter=testimonial_data.matter,
            user_id=testimonial_data.user_id,
            picture_url=final_url,
            type=testimonial_data.type
        )
        
        db.add(db_testimonial)
        db.commit()
        db.refresh(db_testimonial)
        
        return db_testimonial
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating testimonial: {str(e)}"
        )

@router.get("/", response_model=schemas.TestimonialPagination)
def read_testimonials(
    page: int = Query(1, gt=0),
    page_size: int = Query(10, gt=0, le=100),
    db: Session = Depends(get_db)
):
    """Get paginated list of testimonials"""
    offset = (page - 1) * page_size
    
    # Get total count
    total_count = db.query(func.count(models.Testimonial.id)).scalar()
    
    # Get testimonials for current page
    testimonials = db.query(models.Testimonial)\
        .order_by(models.Testimonial.created_at.desc())\
        .offset(offset)\
        .limit(page_size)\
        .all()
    
    total_pages = -(-total_count // page_size)  # Ceiling division
    
    return {
        "items": testimonials,
        "total": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages
    }

@router.put("/{testimonial_id}", response_model=schemas.Testimonial)
async def update_testimonial(
    testimonial_id: int,
    testimonial_data: schemas.TestimonialCreateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Update a testimonial with optional image update via presigned URL"""
    
    if current_user.user_type not in [models.UserType.ADMIN, models.UserType.TEACHER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update testimonials"
        )
    
    db_testimonial = db.query(models.Testimonial)\
        .filter(models.Testimonial.id == testimonial_id)\
        .first()
    
    if db_testimonial is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Testimonial not found"
        )
    
    try:
        s3_client = S3Client()
        
        # Update image if new file provided
        if testimonial_data.picture_file:
            # Delete old image
            TestimonialS3Utils.delete_s3_image(s3_client, db_testimonial.picture_url)
            
            # Set new image URL
            final_url = f"https://{s3_client.bucket_name}.s3.{settings.AWS_REGION}.amazonaws.com/{testimonial_data.picture_file.object_key}"
            db_testimonial.picture_url = final_url
        
        # Update other fields
        db_testimonial.stars = testimonial_data.stars
        db_testimonial.matter = testimonial_data.matter
        db_testimonial.name = testimonial_data.name
        db_testimonial.type = testimonial_data.type
        db_testimonial.user_id = testimonial_data.user_id
        
        db.commit()
        db.refresh(db_testimonial)
        
        return db_testimonial
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating testimonial: {str(e)}"
        )

@router.delete("/{testimonial_id}")
async def delete_testimonial(
    testimonial_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Delete a testimonial and its associated image"""
    
    if current_user.user_type not in [models.UserType.ADMIN, models.UserType.TEACHER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete testimonials"
        )
    
    db_testimonial = db.query(models.Testimonial)\
        .filter(models.Testimonial.id == testimonial_id)\
        .first()
    
    if db_testimonial is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Testimonial not found"
        )
    
    try:
        # Delete image from S3
        s3_client = S3Client()
        TestimonialS3Utils.delete_s3_image(s3_client, db_testimonial.picture_url)
        
        # Delete testimonial from database
        db.delete(db_testimonial)
        db.commit()
        
        return {"message": "Testimonial successfully deleted"}
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting testimonial: {str(e)}"
        )