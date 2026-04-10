from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from ..database import get_db
from ..models import Cart, CartItem, Event, Resources, Theme
from ..auth import get_current_user

router = APIRouter(
    prefix="/cart",
    tags=["cart"],
)

# Pydantic models for request/response
class ResourceCartItem(BaseModel):
    theme_id: int
    resource_id: int
    quantity: int

class EventCartItem(BaseModel):
    event_id: int
    quantity: int

class ResourceDetails(BaseModel):
    id: int
    name: str

class ThemeDetails(BaseModel):
    id: int
    name: str
    price: str

class EventDetails(BaseModel):
    id: int
    name: str
    price: str

class CartItemResponse(BaseModel):
    id: int
    item_type: str
    theme_id: Optional[int] = None
    resource_id: Optional[int] = None
    quantity: Optional[int] = None
    event_id: Optional[int] = None
    
    # Seat availability information for events
    total_seats: Optional[int] = None
    seats_booked: Optional[int] = None
    available_seats: Optional[int] = None  # Calculated field
    
    # Detailed information
    resource: Optional[ResourceDetails] = None
    theme: Optional[ThemeDetails] = None
    event: Optional[EventDetails] = None

    class Config:
        orm_mode = True


# Add resource to cart
@router.post("/add-resource", response_model=CartItemResponse)
def add_resource_to_cart(
    item: ResourceCartItem,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # Get or create user's cart
    cart = db.query(Cart).filter(Cart.user_id == current_user.id).first()
    if not cart:
        cart = Cart(user_id=current_user.id)
        db.add(cart)
        db.commit()
        db.refresh(cart)
    
    # Check if this resource already exists in cart
    existing_item = db.query(CartItem).filter(
        CartItem.cart_id == cart.id,
        CartItem.item_type == "resource",
        CartItem.theme_id == item.theme_id,
        CartItem.resource_id == item.resource_id
    ).first()
    
    if existing_item:
        # Update quantity if it already exists
        existing_item.quantity += item.quantity
        db.commit()
        db.refresh(existing_item)
        return existing_item
    
    # Create new cart item
    new_item = CartItem(
        cart_id=cart.id,
        item_type="resource",
        theme_id=item.theme_id,
        resource_id=item.resource_id,
        quantity=item.quantity
    )
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    return new_item

# Add event to cart
@router.post("/add-event", response_model=CartItemResponse)
def add_event_to_cart(
    item: EventCartItem,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # Get or create user's cart
    cart = db.query(Cart).filter(Cart.user_id == current_user.id).first()
    if not cart:
        cart = Cart(user_id=current_user.id)
        db.add(cart)
        db.commit()
        db.refresh(cart)
    
    # Check if this event already exists in cart
    existing_item = db.query(CartItem).filter(
        CartItem.cart_id == cart.id,
        CartItem.item_type == "event",
        CartItem.event_id == item.event_id
    ).first()
    
    if existing_item:
        # Event already in cart
        existing_item.quantity += item.quantity
        db.commit()
        db.refresh(existing_item)
        return existing_item
    
    # Create new cart item
    new_item = CartItem(
        cart_id=cart.id,
        item_type="event",
        event_id=item.event_id,
        quantity=item.quantity
    )
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    return new_item

# Get all items in cart
@router.get("/items", response_model=List[CartItemResponse])
def get_cart_items(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # Get user's cart
    cart = db.query(Cart).filter(Cart.user_id == current_user.id).first()
    if not cart:
        return []
    
    # Get all items in cart
    cart_items = db.query(CartItem).filter(CartItem.cart_id == cart.id).all()
    
    # Prepare response with details
    result = []
    for item in cart_items:
        item_dict = {
            "id": item.id,
            "item_type": item.item_type,
            "theme_id": item.theme_id,
            "resource_id": item.resource_id,
            "quantity": item.quantity,
            "event_id": item.event_id,
            "resource": None,
            "theme": None,
            "event": None
        }
        
        # Fetch resource details if it's a resource
        if item.item_type == "resource" and item.resource_id:
            resource = db.query(Resources).filter(Resources.id == item.resource_id).first()
            if resource:
                item_dict["resource"] = {
                    "id": resource.id,
                    "name": resource.name,
                    # Add other fields as needed
                }
            
            # Fetch theme details if available
            if item.theme_id:
                theme = db.query(Theme).filter(Theme.id == item.theme_id).first()
                if theme:
                    item_dict["theme"] = {
                        "id": theme.id,
                        "name": theme.name,
                        "price": theme.price
                        # Add other fields as needed
                    }
        
        # Fetch event details if it's an event
        elif item.item_type == "event" and item.event_id:
            event = db.query(Event).filter(Event.id == item.event_id).first()
            if event:
                item_dict["event"] = {
                    "id": event.id,
                    "name": event.title,
                    "price": event.price
                    # Add other fields as needed
                }
        
        result.append(item_dict)
    
    return result

# Update resource quantity in cart
@router.put("/update-resource/{item_id}", response_model=CartItemResponse)
def update_resource_quantity(
    item_id: int,
    new_quantity: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # Get user's cart
    cart = db.query(Cart).filter(Cart.user_id == current_user.id).first()
    if not cart:
        raise HTTPException(status_code=404, detail="Cart not found")
    
    # Get cart item
    item = db.query(CartItem).filter(
        CartItem.id == item_id,
        CartItem.cart_id == cart.id,
    ).first()
    
    if not item:
        raise HTTPException(status_code=404, detail="Item not found in cart")
    
    # Check if item is an event and get event details
    if item.item_type == "event" and item.event_id:
        event = db.query(Event).filter(Event.id == item.event_id).first()
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        
        # Check seat availability for events
        total_seats = event.total_seats
        seats_booked = event.seats_booked
        
        # Optional: Add validation for seat availability
        if total_seats and seats_booked:
            available_seats = total_seats - seats_booked
            if new_quantity > available_seats:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Only {available_seats} seats available. Total seats: {total_seats}, Booked: {seats_booked}"
                )
    
    if new_quantity <= 0:
        # Remove item if quantity is 0 or negative
        db.delete(item)
        db.commit()
        raise HTTPException(status_code=status.HTTP_204_NO_CONTENT)
    
    # Update quantity (for resources) or handle event booking
    if item.item_type == "resource":
        item.quantity = new_quantity
    elif item.item_type == "event":
        # For events, you might want to handle this differently
        # since events typically don't have quantities in the same way
        # You might want to validate booking logic here
        item.quantity = new_quantity  # or handle event booking logic
    
    db.commit()
    db.refresh(item)
    
    # Prepare response with seat information if it's an event
    response_data = {
        "id": item.id,
        "item_type": item.item_type,
        "theme_id": item.theme_id,
        "resource_id": item.resource_id,
        "quantity": item.quantity,
        "event_id": item.event_id,
    }
    
    # Add seat information for events
    if item.item_type == "event" and item.event_id:
        event = db.query(Event).filter(Event.id == item.event_id).first()
        if event:
            response_data.update({
                "total_seats": event.total_seats,
                "seats_booked": event.seats_booked,
                "available_seats": (event.total_seats - event.seats_booked) if event.total_seats and event.seats_booked else None
            })
    
    return CartItemResponse(**response_data)

# Delete item from cart
@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cart_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # Get user's cart
    cart = db.query(Cart).filter(Cart.user_id == current_user.id).first()
    if not cart:
        raise HTTPException(status_code=404, detail="Cart not found")
    
    # Get cart item
    item = db.query(CartItem).filter(
        CartItem.id == item_id,
        CartItem.cart_id == cart.id
    ).first()
    
    if not item:
        raise HTTPException(status_code=404, detail="Item not found in cart")
    
    # Delete item
    db.delete(item)
    db.commit()
    return

# Clear entire cart
@router.delete("/clear", status_code=status.HTTP_204_NO_CONTENT)
def clear_cart(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # Get user's cart
    cart = db.query(Cart).filter(Cart.user_id == current_user.id).first()
    if not cart:
        return
    
    # Delete all items in cart
    db.query(CartItem).filter(CartItem.cart_id == cart.id).delete()
    db.commit()
    return