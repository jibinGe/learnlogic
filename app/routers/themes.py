# routes/themes.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from .. import models, schemas, auth
from ..database import get_db
from ..utils.s3 import S3Client
import uuid
import math
from ..config import settings

router = APIRouter(prefix="/themes", tags=["Themes"])

class ThemeS3Utils:
    ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/gif"]
    ALLOWED_PDF_TYPES = ["application/pdf"]
    ALLOWED_DOC_TYPES = [
        "application/msword",  # .doc
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
        "application/vnd.ms-powerpoint",  # .ppt
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # .pptx
        "application/vnd.ms-excel",  # .xls
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
    ]
    ALLOWED_ZIP_TYPES = ["application/zip", "application/x-zip-compressed"]
    
    @staticmethod
    def get_file_category(content_type: str) -> Optional[str]:
        if content_type in ThemeS3Utils.ALLOWED_IMAGE_TYPES:
            return "images"
        elif content_type in ThemeS3Utils.ALLOWED_PDF_TYPES:
            return "pdfs"
        elif content_type in ThemeS3Utils.ALLOWED_DOC_TYPES:
            return "docs"
        elif content_type in ThemeS3Utils.ALLOWED_ZIP_TYPES:
            return "zips"
        return None

    @staticmethod
    def generate_object_key(theme_id: int, filename: str, category: str) -> str:
        """Generate S3 object key for theme files"""
        ext = filename.split('.')[-1]
        unique_filename = f"{uuid.uuid4()}.{ext}"
        return f"themes/{theme_id}/{category}/{unique_filename}"

    @staticmethod
    def delete_theme_files(s3_client: S3Client, theme_id: int):
        """Delete all files associated with a theme"""
        prefix = f"themes/{theme_id}/"
        try:
            try:
                objects = s3_client.s3_client.list_objects_v2(
                    Bucket=s3_client.bucket_name,
                    Prefix=prefix
                )
                
                if 'Contents' in objects:
                    for obj in objects['Contents']:
                        s3_client.delete_object(obj['Key'])
            except Exception as list_error:
                print(f"Error listing theme files: {list_error}")
                pass
                
        except Exception as e:
            print(f"Error deleting theme files: {e}")

# Presigned URL endpoints for themes
@router.post("/{resource_id}/themes/presigned-url", response_model=schemas.PresignedUrlResponse)
async def get_presigned_url_for_theme(
    resource_id: int,
    request: schemas.PresignedUrlRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Generate presigned URL for uploading theme files"""
    if current_user.user_type != models.UserType.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to upload files"
        )
    
    # Verify resource exists
    resource = db.query(models.Resources).filter(models.Resources.id == resource_id).first()
    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found"
        )
    
    try:
        s3_client = S3Client()
        
        # Determine file category
        category = ThemeS3Utils.get_file_category(request.content_type)
        if not category:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file type: {request.content_type}"
            )
        
        # Generate object key (we'll use a temporary theme_id, will be updated when theme is created)
        temp_theme_id = f"temp_{uuid.uuid4().hex[:8]}"
        object_key = f"themes/{temp_theme_id}/{category}/{uuid.uuid4()}.{request.filename.split('.')[-1]}"
        
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

@router.post("/{resource_id}/themes/multipart-upload", response_model=schemas.MultipartUploadResponse)
async def initiate_multipart_upload_for_theme(
    resource_id: int,
    request: schemas.MultipartUploadRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Initiate multipart upload for large theme files"""
    if current_user.user_type != models.UserType.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to upload files"
        )
    
    # Verify resource exists
    resource = db.query(models.Resources).filter(models.Resources.id == resource_id).first()
    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found"
        )
    
    try:
        s3_client = S3Client()
        
        # Determine file category
        category = ThemeS3Utils.get_file_category(request.content_type)
        if not category:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file type: {request.content_type}"
            )
        
        # Generate object key
        temp_theme_id = f"temp_{uuid.uuid4().hex[:8]}"
        object_key = f"themes/{temp_theme_id}/{category}/{uuid.uuid4()}.{request.filename.split('.')[-1]}"
        
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

# CRUD endpoints
@router.post("/{resource_id}", response_model=schemas.Theme)
async def create_theme(
    resource_id: int,
    theme_data: schemas.ThemeCreateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Create a new theme with files uploaded via presigned URLs"""
    if current_user.user_type != models.UserType.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to create themes"
        )

    # Verify resource exists
    db_resource = db.query(models.Resources).filter(models.Resources.id == resource_id).first()
    if not db_resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found"
        )

    try:
        # Initialize theme
        db_theme = models.Theme(
            name=theme_data.name,
            resource_id=resource_id,
            price=theme_data.price,
            type=theme_data.type,
            data={
                "images": [],
                "pdfs": [],
                "docs": [],
                "zips": []
            }
        )
        db.add(db_theme)
        db.flush()  # Get theme_id without committing

        s3_client = S3Client()
        theme_files_data = {
            "images": [],
            "pdfs": [],
            "docs": [],
            "zips": []
        }
        
        # Process uploaded files
        for file_info in theme_data.files:
            try:
                # Determine category from content type
                category = ThemeS3Utils.get_file_category(file_info.content_type)
                if not category:
                    print(f"Skipping file {file_info.original_filename}: Unsupported type {file_info.content_type}")
                    continue

                # Generate new object key with proper theme ID
                new_object_key = ThemeS3Utils.generate_object_key(
                    db_theme.id, 
                    file_info.original_filename, 
                    category
                )
                
                # Copy file from temp location to final location
                copy_source = {
                    'Bucket': s3_client.bucket_name,
                    'Key': file_info.object_key
                }
                
                s3_client.s3_client.copy_object(
                    CopySource=copy_source,
                    Bucket=s3_client.bucket_name,
                    Key=new_object_key,
                    ContentType=file_info.content_type
                )
                
                # Delete temporary file
                s3_client.delete_object(file_info.object_key)
                
                # Generate final URL
                final_url = f"https://{s3_client.bucket_name}.s3.{settings.AWS_REGION}.amazonaws.com/{new_object_key}"
                
                # Create file data
                file_data = {
                    "url": final_url,
                    "file_type": file_info.content_type,
                    "original_name": file_info.original_filename,
                    "category": category
                }
                
                # Add to the appropriate category
                theme_files_data[category].append(file_data)
                print(f"Processed {file_info.original_filename} -> {final_url}")
                
            except Exception as process_error:
                print(f"Error processing file {file_info.original_filename}: {str(process_error)}")
                # Continue with other files instead of failing completely
                continue

        # Update theme data with file information
        db_theme.data = theme_files_data
        
        # Commit all changes
        db.commit()
        db.refresh(db_theme)
        
        print(f"Theme created successfully with data: {db_theme.data}")
        return db_theme

    except Exception as e:
        print(f"Error in create_theme: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating theme: {str(e)}"
        )
    
@router.get("/{resource_id}/themes", response_model=schemas.PaginatedResponse[schemas.ThemeResponse])
def get_themes_by_resource(
    resource_id: int,
    page: int = Query(1, gt=0),
    page_size: int = Query(10, gt=0, le=100),
    db: Session = Depends(get_db)
):
    """Get all themes for a specific resource with pagination"""
    
    # Verify resource exists
    db_resource = db.query(models.Resources).filter(models.Resources.id == resource_id).first()
    if not db_resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found"
        )
    
    # Calculate offset
    offset = (page - 1) * page_size
    
    # Get total count of themes for this resource
    total_count = db.query(func.count(models.Theme.id))\
        .filter(models.Theme.resource_id == resource_id)\
        .scalar()
    
    # Get themes for current page
    themes = db.query(models.Theme)\
        .filter(models.Theme.resource_id == resource_id)\
        .order_by(models.Theme.created_at.desc())\
        .offset(offset)\
        .limit(page_size)\
        .all()
    
    # Calculate total pages
    total_pages = -(-total_count // page_size)  # Ceiling division
    
    # Convert SQLAlchemy models to Pydantic models
    theme_responses = []
    for theme in themes:
        theme_data = schemas.ThemeFileData(
            images=[schemas.FileData(**img) for img in theme.data.get('images', [])],
            pdfs=[schemas.FileData(**pdf) for pdf in theme.data.get('pdfs', [])],
            docs=[schemas.FileData(**doc) for doc in theme.data.get('docs', [])],
            zips=[schemas.FileData(**zip_file) for zip_file in theme.data.get('zips', [])]
        )
        
        theme_response = schemas.ThemeResponse(
            id=theme.id,
            name=theme.name,
            data=theme_data,
            price=theme.price,
            created_at=theme.created_at,
            resource_id=theme.resource_id,
            type = theme.type
        )
        theme_responses.append(theme_response)
    
    return {
        "items": theme_responses,
        "total": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages
    }

@router.get("/", response_model=List[schemas.Theme])
def read_themes(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    resource_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get list of themes with optional resource filter"""
    query = db.query(models.Theme)
    
    if resource_id:
        query = query.filter(models.Theme.resource_id == resource_id)
    
    themes = query.offset(skip).limit(limit).all()
    return themes


@router.get("/{theme_id}", response_model=schemas.Theme)
def read_theme(
    theme_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific theme by ID"""
    theme = db.query(models.Theme).filter(models.Theme.id == theme_id).first()
    if not theme:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Theme not found"
        )
    return theme

# @router.get("/by-name/{theme_name}", response_model=schemas.Theme)
# def read_theme_by_name(
#     theme_name: str,
#     db: Session = Depends(get_db)
# ):
#     """Get a specific theme by name"""
#     theme = db.query(models.Theme).filter(models.Theme.name == theme_name).first()
#     if not theme:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail=f"Theme with name '{theme_name}' not found"
#         )
#     return theme

@router.get("/by-name/{theme_name}", response_model=schemas.Theme)
def read_theme_by_name(
    theme_name: str,
    db: Session = Depends(get_db)
):
    """Get a specific theme by name (supports both original format and lowercase with underscores)"""
    
    def normalize_name(name: str) -> str:
        """Convert name to lowercase, trim whitespace, and normalize all separators to underscores"""
        return name.strip().lower().replace(' ', '_').replace('-', '_')
    
    # First, try exact match with the provided name
    theme = db.query(models.Theme).filter(models.Theme.name == theme_name).first()
    
    if not theme:
        # If exact match fails, try flexible matching
        # Get all themes and check for normalized matches
        all_themes = db.query(models.Theme).all()
        
        # Normalize the input theme_name
        normalized_input = normalize_name(theme_name)
        
        for db_theme in all_themes:
            # Normalize the database theme name and compare
            if normalize_name(db_theme.name) == normalized_input:
                theme = db_theme
                break
    
    if not theme:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Theme with name '{theme_name}' not found"
        )
    
    return theme

@router.put("/{theme_id}", response_model=schemas.Theme)
async def update_theme(
    theme_id: int,
    theme_data: schemas.ThemeCreateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Update a theme with files uploaded via presigned URLs"""
    if current_user.user_type != models.UserType.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update themes"
        )

    db_theme = db.query(models.Theme).filter(models.Theme.id == theme_id).first()
    if not db_theme:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Theme not found"
        )

    try:
        s3_client = S3Client()
        
        # Handle file updates if provided
        if theme_data.files:
            # Try to delete existing files
            try:
                ThemeS3Utils.delete_theme_files(s3_client, theme_id)
            except Exception as delete_error:
                print(f"Warning: Could not delete existing files: {delete_error}")
            
            # Reset file data
            theme_files_data = {
                "images": [],
                "pdfs": [],
                "docs": [],
                "zips": []
            }
            
            # Process new files
            for file_info in theme_data.files:
                try:
                    # Determine category from content type
                    category = ThemeS3Utils.get_file_category(file_info.content_type)
                    if not category:
                        print(f"Skipping file {file_info.original_filename}: Unsupported type")
                        continue

                    # Generate new object key
                    new_object_key = ThemeS3Utils.generate_object_key(
                        theme_id, 
                        file_info.original_filename, 
                        category
                    )
                    
                    # Copy file from temp location to final location
                    copy_source = {
                        'Bucket': s3_client.bucket_name,
                        'Key': file_info.object_key
                    }
                    
                    s3_client.s3_client.copy_object(
                        CopySource=copy_source,
                        Bucket=s3_client.bucket_name,
                        Key=new_object_key,
                        ContentType=file_info.content_type
                    )
                    
                    # Delete temporary file
                    s3_client.delete_object(file_info.object_key)
                    
                    # Generate final URL
                    final_url = f"https://{s3_client.bucket_name}.s3.{settings.AWS_REGION}.amazonaws.com/{new_object_key}"
                    
                    # Create file data
                    file_data = {
                        "url": final_url,
                        "file_type": file_info.content_type,
                        "original_name": file_info.original_filename,
                        "category": category
                    }
                    
                    # Add to the appropriate category
                    theme_files_data[category].append(file_data)
                    print(f"Updated {file_info.original_filename} -> {final_url}")
                    
                except Exception as upload_error:
                    print(f"Error processing file {file_info.original_filename}: {str(upload_error)}")
                    continue
            
            # Update theme data with new file information
            db_theme.data = theme_files_data

        # Update theme properties
        db_theme.name = theme_data.name
        db_theme.price = theme_data.price
        db_theme.type = theme_data.type
        
        db.commit()
        db.refresh(db_theme)
        return db_theme

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating theme: {str(e)}"
        )

@router.delete("/{theme_id}")
async def delete_theme(
    theme_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Delete a theme and its associated files"""
    if current_user.user_type != models.UserType.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete themes"
        )

    db_theme = db.query(models.Theme).filter(models.Theme.id == theme_id).first()
    if not db_theme:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Theme not found"
        )

    try:
        # Try to delete files from S3
        try:
            s3_client = S3Client()
            ThemeS3Utils.delete_theme_files(s3_client, theme_id)
        except Exception as s3_error:
            print(f"Warning: Could not delete S3 files: {s3_error}")
        
        # Delete theme from database
        db.delete(db_theme)
        db.commit()
        
        return {"message": "Theme and associated files deleted successfully"}

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting theme: {str(e)}"
        )