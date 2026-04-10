# routes/resources.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from typing import List
from .. import models, schemas, auth
from ..database import get_db

router = APIRouter(prefix="/resources", tags=["Resources"])

@router.post("/", response_model=schemas.Resource)
def create_resource(
    resource: schemas.ResourceCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if current_user.user_type != models.UserType.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Create resource
    db_resource = models.Resources(
        name=resource.name,
        data=resource.data
    )
    db.add(db_resource)
    db.commit()
    db.refresh(db_resource)
    return db_resource

@router.get("/", response_model=List[schemas.Resource])
def read_resources(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    resources = db.query(models.Resources).offset(skip).limit(limit).all()
    return resources

@router.get("/resources_with_theme", response_model=List[schemas.ResourceWithThemes])
def read_resources(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Get list of resources with their associated themes"""
    resources = db.query(models.Resources)\
        .options(joinedload(models.Resources.themes))\
        .order_by(models.Resources.created_at.asc())\
        .offset(skip)\
        .limit(limit)\
        .all()
    
    return resources

@router.get("/{resource_id}", response_model=schemas.Resource)
def read_resource(
    resource_id: int,
    db: Session = Depends(get_db)
):
    db_resource = db.query(models.Resources).filter(
        models.Resources.id == resource_id
    ).first()
    if db_resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return db_resource

@router.put("/{resource_id}", response_model=schemas.Resource)
def update_resource(
    resource_id: int,
    resource: schemas.ResourceUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if current_user.user_type != models.UserType.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    db_resource = db.query(models.Resources).filter(
        models.Resources.id == resource_id
    ).first()
    if db_resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    
    # Update resource fields
    db_resource.name = resource.name
    db_resource.data = resource.data
    
    # Remove theme operations - manage themes separately
    # Since the payload doesn't include themes information
    
    db.commit()
    db.refresh(db_resource)
    return db_resource

@router.delete("/{resource_id}")
def delete_resource(
    resource_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if current_user.user_type != models.UserType.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Delete themes first (this should happen automatically with cascade)
    db.query(models.Theme).filter(models.Theme.resource_id == resource_id).delete()
    
    # Delete resource
    db_resource = db.query(models.Resources).filter(
        models.Resources.id == resource_id
    ).first()
    if db_resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    
    db.delete(db_resource)
    db.commit()
    return {"detail": "Resource deleted"}