from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from sqlalchemy import func
# Import your models and database dependency
from ..models import User, Purchase, PurchaseItem, PurchaseStatus
from ..database import get_db # Assuming you have a get_db dependency

from pydantic import BaseModel
from typing import Optional

class UserBase(BaseModel):
    id: int
    email: str
    full_name: Optional[str] = None
    title: Optional[str] = None
    school: Optional[str] = None
    job_title: Optional[str] = None
    user_type: str

    class Config:
        from_attributes = True

# Extended Schema with Booking Count
class UserBookingDetails(UserBase):
    booked_quantity: int

router = APIRouter(prefix="/admin", tags=["Admin"])

@router.get("/events/{event_id}/users", response_model=List[UserBookingDetails])
def get_users_for_event(event_id: int, db: Session = Depends(get_db)):
    """
    Returns users who booked the event, along with the total number of seats they booked.
    """
    results = (
        db.query(User, func.sum(PurchaseItem.quantity).label("total_quantity"))
        .join(Purchase, Purchase.user_id == User.id)
        .join(PurchaseItem, PurchaseItem.purchase_id == Purchase.id)
        .filter(
            PurchaseItem.item_type == "event",
            PurchaseItem.event_id == event_id,
            Purchase.status == PurchaseStatus.COMPLETED
        )
        .group_by(User.id)  # Combine multiple purchases by the same user
        .all()
    )

    # Transform the SQLAlchemy result tuples (User, int) into the Pydantic schema
    response_data = []
    for user, quantity in results:
        # We define a dictionary merging user data + the quantity
        user_data = user.__dict__
        user_data["booked_quantity"] = quantity or 0 # Handle None if quantity is null
        response_data.append(user_data)

    return response_data

# ---------------------------------------------------------
# 2. Get Users + Quantity for a RESOURCE
# ---------------------------------------------------------
@router.get("/resources/{resource_id}/users", response_model=List[UserBookingDetails])
def get_users_for_resource(resource_id: int, db: Session = Depends(get_db)):
    """
    Returns users who bought the resource, along with the quantity purchased.
    """
    results = (
        db.query(User, func.sum(PurchaseItem.quantity).label("total_quantity"))
        .join(Purchase, Purchase.user_id == User.id)
        .join(PurchaseItem, PurchaseItem.purchase_id == Purchase.id)
        .filter(
            PurchaseItem.item_type == "resource",
            PurchaseItem.resource_id == resource_id,
            Purchase.status == PurchaseStatus.COMPLETED
        )
        .group_by(User.id)
        .all()
    )

    response_data = []
    for user, quantity in results:
        user_data = user.__dict__
        user_data["booked_quantity"] = quantity or 0
        response_data.append(user_data)

    return response_data