from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from .. import models, schemas, auth
from ..database import get_db

router = APIRouter(prefix="/billing-address", tags=["Billing Address"])

# Add billing address for the current user
@router.post("/", response_model=schemas.BillingAddressResponse)
def add_billing_address(
    billing_data: schemas.BillingAddressUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    # Update the user's billing address
    current_user.billing_address = billing_data.billing_address
    db.commit()
    db.refresh(current_user)
    
    return {
        "user_id": current_user.id,
        "billing_address": current_user.billing_address
    }

# Get the current user's billing address
@router.get("/", response_model=schemas.BillingAddressResponse)
def get_billing_address(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if not current_user.billing_address:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Billing address not found"
        )
    
    return {
        "user_id": current_user.id,
        "billing_address": current_user.billing_address
    }

# Update the current user's billing address
@router.put("/", response_model=schemas.BillingAddressResponse)
def update_billing_address(
    billing_data: schemas.BillingAddressUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if not current_user.billing_address:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Billing address not found, use POST to create"
        )
    
    # Update the billing address
    current_user.billing_address = billing_data.billing_address
    db.commit()
    db.refresh(current_user)
    
    return {
        "user_id": current_user.id,
        "billing_address": current_user.billing_address
    }

# Delete the current user's billing address
@router.delete("/", status_code=status.HTTP_204_NO_CONTENT)
def delete_billing_address(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if not current_user.billing_address:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Billing address not found"
        )
    
    # Remove the billing address
    current_user.billing_address = None
    db.commit()
    
    return

# Admin endpoints
# Get billing address for any user (admin only)
@router.get("/{user_id}", response_model=schemas.BillingAddressResponse)
def admin_get_billing_address(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    # Check admin permissions
    if current_user.user_type != models.UserType.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this resource"
        )
    
    # Get the user
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if not user.billing_address:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Billing address not found for this user"
        )
    
    return {
        "user_id": user.id,
        "billing_address": user.billing_address
    }

# Update billing address for any user (admin only)
@router.put("/{user_id}", response_model=schemas.BillingAddressResponse)
def admin_update_billing_address(
    user_id: int,
    billing_data: schemas.BillingAddressUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    # Check admin permissions
    if current_user.user_type != models.UserType.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to perform this action"
        )
    
    # Get the user
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Update the billing address
    user.billing_address = billing_data.billing_address
    db.commit()
    db.refresh(user)
    
    return {
        "user_id": user.id,
        "billing_address": user.billing_address
    }