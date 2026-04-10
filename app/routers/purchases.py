from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from pydantic import BaseModel
from datetime import datetime

from ..database import get_db
from ..models import Purchase, PurchaseItem, Cart, CartItem, Event, Resources, Theme, PurchaseStatus, EventStatus
from ..auth import get_current_user
from ..utils.ses import SESService
from ..schemas import EmailRequest  # Make sure this import exists
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/purchases",
    tags=["purchases"],
)
ses_service = SESService()

# Pydantic models for request/response
class ResourceDetails(BaseModel):
    id: int
    name: str

class ThemeDetails(BaseModel):
    id: int
    name: str
    price: str
    data: Optional[Dict] = None

class EventDetails(BaseModel):
    id: int
    name: str
    price: str
    time : str
    location : str
    date : str

class PurchaseItemResponse(BaseModel):
    id: int
    item_type: str
    theme_id: Optional[int] = None
    resource_id: Optional[int] = None
    quantity: Optional[int] = None
    event_id: Optional[int] = None
    price: float
    
    # Detailed information
    resource: Optional[ResourceDetails] = None
    theme: Optional[ThemeDetails] = None
    event: Optional[EventDetails] = None

    class Config:
        orm_mode = True

class Address(BaseModel):
    line1: Optional[str] = None
    line2: Optional[str] = None
    city: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None

class BillingDetails(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[Address] = None

class PaymentInfo(BaseModel):
    payment_method: str
    transaction_id: Optional[str] = None
    card_brand: Optional[str] = None
    card_last4: Optional[str] = None
    billing_details: Optional[BillingDetails] = None # Added this


class PurchaseResponse(BaseModel):
    id: int
    user_id: int
    total_amount: float
    transaction_id: Optional[str] = None
    payment_method: Optional[str] = None
    status: str
    created_at: datetime
    purchase_items: List[PurchaseItemResponse]

    class Config:
        orm_mode = True

def format_address_component(component: str, is_postcode: bool = False) -> str:
    """Format address component with proper capitalization"""
    if not component:
        return ""
    
    # Keep postcode in uppercase
    if is_postcode:
        return component.upper()
    
    # For other components, title case each word
    return component.title()

# Create a purchase from the cart
@router.post("/checkout", response_model=PurchaseResponse)
async def checkout(
    payment_info: PaymentInfo,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    import stripe
    from app.config import settings
    
    customer_email = current_user.email
    customer_name = current_user.full_name

    if payment_info.billing_details:
        if payment_info.billing_details.email:
            customer_email = payment_info.billing_details.email
        if payment_info.billing_details.name:
            customer_name = payment_info.billing_details.name

    logger.info(f"Processing checkout for: {customer_email}")

    # DEBUG LOGGING
    logger.info("=== CHECKOUT DEBUG START ===")
    logger.info(f"transaction_id: {payment_info.transaction_id}")
    logger.info(f"payment_method: {payment_info.payment_method}")
    logger.info(f"card_brand: {payment_info.card_brand}")
    logger.info(f"card_last4: {payment_info.card_last4}")
    
    # Get user's cart
    cart = db.query(Cart).filter(Cart.user_id == current_user.id).first()
    if not cart:
        raise HTTPException(status_code=404, detail="Cart is empty")

    # Get all items in the cart
    cart_items = db.query(CartItem).filter(CartItem.cart_id == cart.id).all()
    if not cart_items:
        raise HTTPException(status_code=404, detail="Cart is empty")

    total_amount = 0.0
    order_items = []

    # Extract the original Stripe payment intent ID for API calls
    original_payment_intent_id = payment_info.transaction_id
    custom_transaction_id = payment_info.transaction_id
    
    if payment_info.transaction_id:
        if payment_info.transaction_id.startswith('lgc_pi_'):
            # Frontend already converted it, extract original
            original_payment_intent_id = payment_info.transaction_id.replace('lgc_', '')
            custom_transaction_id = payment_info.transaction_id
            logger.info(f"Using custom transaction ID: {custom_transaction_id}")
        elif payment_info.transaction_id.startswith('pi_'):
            # Frontend sent original, we convert it
            original_payment_intent_id = payment_info.transaction_id
            custom_transaction_id = payment_info.transaction_id.replace('pi_', 'lgc_pi_')
            logger.info(f"Transaction ID converted: {payment_info.transaction_id} -> {custom_transaction_id}")

    # Get card details and billing address from Stripe
    payment_method_display = "Card payment"
    card_brand = ""
    billing_address_dict = None
    
    # First, try to use card details sent from frontend
    if payment_info.card_brand and payment_info.card_last4:
        card_brand = payment_info.card_brand.capitalize()
        payment_method_display = f"{card_brand} ending in {payment_info.card_last4}"
        logger.info(f"Card details from frontend: {payment_method_display}")
    else:
        # Fallback: Get from Stripe API using ORIGINAL payment intent ID
        logger.info("No card details from frontend, trying Stripe API...")
        try:
            if original_payment_intent_id and original_payment_intent_id.startswith('pi_'):
                stripe.api_key = settings.STRIPE_SECRET_KEY
                
                # Retrieve the payment intent using ORIGINAL ID with expanded charge data
                logger.info(f"Retrieving payment intent: {original_payment_intent_id}")
                intent = stripe.PaymentIntent.retrieve(
                    original_payment_intent_id,
                    expand=['latest_charge.payment_method_details', 'latest_charge.billing_details']
                )
                logger.info(f"Payment intent retrieved: {intent.id}, status: {intent.status}")
                
                # Extract billing address from payment intent
                if hasattr(intent, 'shipping') and intent.shipping:
                    billing_address_dict = {
                        'line1': intent.shipping.address.line1 if intent.shipping.address else '',
                        'line2': intent.shipping.address.line2 if intent.shipping.address else '',
                        'city': intent.shipping.address.city if intent.shipping.address else '',
                        'state': intent.shipping.address.state if intent.shipping.address else '',
                        'postal_code': intent.shipping.address.postal_code if intent.shipping.address else '',
                        'country': intent.shipping.address.country if intent.shipping.address else '',
                    }
                    logger.info(f"Billing address extracted: {billing_address_dict}")
                
                # Get payment method details from the latest charge
                if hasattr(intent, 'latest_charge') and intent.latest_charge:
                    charge = intent.latest_charge if not isinstance(intent.latest_charge, str) else None
                    logger.info(f"Latest charge type: {type(charge)}")
                    
                    if charge and hasattr(charge, 'billing_details') and charge.billing_details:
                        billing_details = charge.billing_details
                        if hasattr(billing_details, 'address') and billing_details.address:
                            addr = billing_details.address
                            billing_address_dict = {
                                'line1': addr.line1 or '',
                                'line2': addr.line2 or '',
                                'city': addr.city or '',
                                'state': addr.state or '',
                                'postal_code': addr.postal_code or '',
                                'country': addr.country or '',
                            }
                            logger.info(f"Billing address from charge.billing_details: {billing_address_dict}")
                        else:
                            logger.warning("No address found in billing_details")
                    else:
                        logger.warning("No billing_details found in charge")

                    if charge and hasattr(charge, 'payment_method_details'):
                        pm_details = charge.payment_method_details
                        logger.info(f"Payment method type: {pm_details.type}")
                        
                        if pm_details.type == 'card' and hasattr(pm_details, 'card') and pm_details.card:
                            card_brand = pm_details.card.brand.capitalize()
                            last4 = pm_details.card.last4
                            payment_method_display = f"{card_brand} ending in {last4}"
                            logger.info(f"Card details from Stripe: {payment_method_display}")
                        else:
                            payment_method_display = f"{pm_details.type.capitalize()} payment"
                            logger.info(f"Non-card payment method: {pm_details.type}")
                    else:
                        logger.warning("No payment_method_details found in latest_charge")
    
                else:
                    logger.warning(f"No latest_charge found for payment intent: {original_payment_intent_id}")
            else:
                logger.warning(f"Invalid payment intent ID format: {original_payment_intent_id}")
                    
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error: {str(e)}", exc_info=True)
        except Exception as e:
            logger.error(f"Error retrieving payment details: {str(e)}", exc_info=True)

    logger.info(f"Final payment_method_display: {payment_method_display}")
    logger.info(f"Final transaction_id: {custom_transaction_id}")
    logger.info("=== CHECKOUT DEBUG END ===")


    # Helper function to format address components
    def format_address_component(component: str, is_postcode: bool = False) -> str:
        """Format address component with proper capitalization"""
        if not component:
            return ""
        
        # Keep postcode in uppercase
        if is_postcode:
            return component.upper()
        
        # For other components, title case each word
        return component.title()

    # Format billing address
    billing_address_formatted = ""
    if payment_info.billing_details and payment_info.billing_details.address:
        # Use address from Frontend Payload
        addr = payment_info.billing_details.address
        address_parts = [
            addr.line1, addr.line2, addr.city, 
            addr.postal_code.upper() if addr.postal_code else None, 
            addr.country
        ]
        billing_address_formatted = ", ".join([p.title() if p and len(p)>2 else p for p in address_parts if p])
    else:
        if billing_address_dict:
            address_parts = []
            if billing_address_dict.get('line1'):
                address_parts.append(format_address_component(billing_address_dict['line1']))
            if billing_address_dict.get('line2'):
                address_parts.append(format_address_component(billing_address_dict['line2']))
            if billing_address_dict.get('city'):
                address_parts.append(format_address_component(billing_address_dict['city']))
            if billing_address_dict.get('state'):
                address_parts.append(format_address_component(billing_address_dict['state']))
            if billing_address_dict.get('postal_code'):
                address_parts.append(format_address_component(billing_address_dict['postal_code'], is_postcode=True))
            if billing_address_dict.get('country'):
                address_parts.append(format_address_component(billing_address_dict['country']))
            billing_address_formatted = ", ".join(address_parts)
        # elif current_user.billing_address:
        #     billing_address_formatted = current_user.billing_address

    # Create purchase
    new_purchase = Purchase(
        user_id=current_user.id,
        total_amount=0,
        payment_method=payment_method_display,
        transaction_id=custom_transaction_id,
        status=PurchaseStatus.COMPLETED
    )
    
    db.add(new_purchase)
    db.flush()

    for cart_item in cart_items:
        price = 0.0
        item_details = {}

        # Resource
        if cart_item.item_type == "resource" and cart_item.theme_id:
            theme = db.query(Theme).filter(Theme.id == cart_item.theme_id).first()
            resource = db.query(Resources).filter(Resources.id == cart_item.resource_id).first()
            
            if theme:
                try:
                    # Handle various free/zero price formats
                    price_str = str(theme.price).strip().lower()
                    if price_str in ['free', '0', '0.0', '0.00', '']:
                        unit_price = 0.0
                    else:
                        unit_price = float(theme.price)
                    
                    price = unit_price * cart_item.quantity
                    
                    item_details = {
                        "description": f"{theme.name}",
                        "subtitle": f"{resource.name if resource else 'Resource'}",
                        "quantity": cart_item.quantity,
                        "unit_price": unit_price,
                        "subtotal": price,
                        "is_free": unit_price == 0.0
                    }
                    order_items.append(item_details)
                except (ValueError, TypeError):
                    unit_price = 0.0
                    price = 0.0
                    item_details = {
                        "description": f"{theme.name}",
                        "subtitle": f"{resource.name if resource else 'Resource'}",
                        "quantity": cart_item.quantity,
                        "unit_price": 0.0,
                        "subtotal": 0.0,
                        "is_free": True
                    }
                    order_items.append(item_details)

        # Event
        elif cart_item.item_type == "event" and cart_item.event_id:
            event = db.query(Event).filter(Event.id == cart_item.event_id).first()
            if event:
                if event.status not in [EventStatus.ACTIVE, EventStatus.UPCOMING]:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Event '{event.title}' is not available for booking"
                    )

                if event.total_seats is not None:
                    remaining = event.total_seats - event.seats_booked
                    if remaining < cart_item.quantity:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Only {remaining} seat(s) left for event '{event.title}'"
                        )

                    event.seats_booked += cart_item.quantity
                    if event.seats_booked >= event.total_seats:
                        event.status = EventStatus.ALL_SEATS_BOOKED

                try:
                    # Handle various free/zero price formats
                    price_str = str(event.price).strip().lower()
                    if price_str in ['free', '0', '0.0', '0.00', '']:
                        unit_price = 0.0
                    else:
                        unit_price = float(event.price)
                    
                    price = unit_price * cart_item.quantity
                    
                    item_details = {
                        "description": f"{event.title}",
                        "subtitle": f"{event.qualification} {event.exam_board} {event.subject} • {event.type}",
                        "quantity": cart_item.quantity,
                        "unit_price": unit_price,
                        "subtotal": price,
                        "is_free": unit_price == 0.0
                    }
                    order_items.append(item_details)
                except (ValueError, TypeError):
                    unit_price = 0.0
                    price = 0.0
                    item_details = {
                        "description": f"{event.title}",
                        "subtitle": f"{event.qualification} {event.exam_board} {event.subject} • {event.type}",
                        "quantity": cart_item.quantity,
                        "unit_price": 0.0,
                        "subtotal": 0.0,
                        "is_free": True
                    }
                    order_items.append(item_details)

        purchase_item = PurchaseItem(
            purchase_id=new_purchase.id,
            item_type=cart_item.item_type,
            theme_id=cart_item.theme_id,
            resource_id=cart_item.resource_id,
            quantity=cart_item.quantity,
            event_id=cart_item.event_id,
            price=price
        )
        db.add(purchase_item)
        total_amount += price

    new_purchase.total_amount = total_amount
    db.query(CartItem).filter(CartItem.cart_id == cart.id).delete()

    db.commit()
    db.refresh(new_purchase)

    display_order_id = custom_transaction_id.replace("pi_", "") if custom_transaction_id else "N/A"

    # Send order confirmation email
    try:
        # Generate order items HTML rows
        order_items_html = ""
        for item in order_items:
            price_display = "FREE" if item.get('is_free', False) else f"£{item['unit_price']:.2f}"
            subtotal_display = "FREE" if item.get('is_free', False) else f"£{item['subtotal']:.2f}"
            
            order_items_html += f"""
            <tr>
                <td style="padding: 12px;">
                    <div style="font-weight: 600; color: #333; margin-bottom: 4px;">{item['description']}</div>
                    <div style="font-size: 13px; color: #666;">{item['subtitle']}</div>
                </td>
                <td style="padding: 12px; text-align: center; color: #333;">{item['quantity']}</td>
                <td style="padding: 12px; text-align: right; color: #333;">{price_display}</td>
                <td style="padding: 12px 0 12px 12px; text-align: right; font-weight: 600; color: #333;">{subtotal_display}</td>
            </tr>
            """

        # Generate plain text version
        order_items_text = ""
        for item in order_items:
            price_display = "FREE" if item.get('is_free', False) else f"£{item['unit_price']:.2f}"
            subtotal_display = "FREE" if item.get('is_free', False) else f"£{item['subtotal']:.2f}"
            
            order_items_text += f"{item['description']}\n{item['subtitle']}\n"
            order_items_text += f"Qty: {item['quantity']} × {price_display} = {subtotal_display}\n\n"

        # Format total amount display
        total_display = "FREE" if total_amount == 0.0 else f"£{total_amount:.2f}"

        order_email = EmailRequest(
            to_addresses=[customer_email], # CHANGED: Uses frontend email
            subject=f"Order Confirmation - Order no: {display_order_id}",
            body_text=f"""Dear {customer_name},

Thank you for placing your order with us.
Your order number is {display_order_id}.

Order Summary:
{order_items_text}

Total amount: {total_display}

Payment details:
Card: {payment_method_display}

Billing details:
{customer_name}
{billing_address_formatted}

Best wishes
The Learnogic team
cultivating excellence

© Learnogic 2025 • All rights reserved.""",
            body_html=f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700&display=swap" rel="stylesheet">
            </head>
            <body style="margin: 0; padding: 0; font-family: 'Montserrat', Arial, sans-serif; background-color: #f5f5f5;">
                <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f5f5f5; padding: 20px 0;">
                    <tr>
                        <td align="center">
                            <table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                                
                                <!-- Logo Header -->
                                <tr>
                                    <td style="padding: 30px 40px; text-align: center; background-color: #ffffff;">
                                        <img src="https://s3.ap-south-1.amazonaws.com/learnogic.com/static/logo.jpeg" alt="Learnogic" style="height: 50px; width: auto;">
                                    </td>
                                </tr>
                                
                                <!-- Content -->
                                <tr>
                                    <td style="padding: 0 40px 40px 40px;">
                                        
                                        <p style="font-size: 14px; color: #333; margin-bottom: 10px;">Dear {customer_name},</p>
                                        
                                        <p style="font-size: 14px; color: #666; line-height: 1.6; margin-bottom: 10px;">Thank you for placing your order with us.</p>
                                        
                                        <p style="font-size: 14px; color: #666; line-height: 1.6; margin-bottom: 30px;">Your order number is <strong style="color: #333;">{display_order_id}</strong>.</p>
                                        
                                        <!-- Order Summary Label -->
                                        <div style="margin-bottom: 15px; padding-bottom: 10px; border-bottom: 2px solid #333;">
                                            <span style="font-size: 13px; color: #333; letter-spacing: 1px;">Order Summary</span>
                                        </div>
                                        
                                        <!-- Order Items Table -->
                                        <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom: 20px; border-collapse: collapse;">
                                            <thead>
                                                <tr style="border-bottom: 0px solid #333;">
                                                    <th style="padding: 12px 12px 12px 12px; text-align: left; font-size: 13px; font-weight: 600; color: #333;">Description</th>
                                                    <th style="padding: 12px; text-align: center; font-size: 13px; font-weight: 600; color: #333;">Qty</th>
                                                    <th style="padding: 12px; text-align: right; font-size: 13px; font-weight: 600; color: #333;">Price</th>
                                                    <th style="padding: 12px 0 12px 12px; text-align: right; font-size: 13px; font-weight: 600; color: #333;">Subtotal</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {order_items_html}
                                            </tbody>
                                        </table>
                                        
                                        <!-- Total -->
                                        <table width="100%" cellpadding="0" cellspacing="0" style="margin: 30px 0;">
                                            <tr>
                                                <td style="padding: 15px 0; text-align: right; font-size: 15px; font-weight: 600; color: #333; border-top: 2px solid #333;">
                                                    Total amount
                                                </td>
                                                <td style="padding: 15px 0 15px 20px; text-align: right; font-size: 15px; font-weight: 600; color: #333; border-top: 2px solid #333; width: 120px;">
                                                    {total_display}
                                                </td>
                                            </tr>
                                        </table>

                                        <p style="font-size: 14px; color: #666; line-height: 1.6; margin-bottom: 10px;"><strong>Purchased an event?</strong></p>
                                        <p style="font-size: 14px; color: #666; line-height: 1.6; margin-bottom: 10px;">Full event details will be sent to your email address a few days before the event date. Please remember to check your inbox and your spam/junk folder to make sure you don't miss them.</p>
                                        <p style="font-size: 14px; color: #666; line-height: 1.6; margin-bottom: 10px;"><strong>Purchased a resource?</strong></p>
                                        <p style="font-size: 14px; color: #666; line-height: 1.6; margin-bottom: 10px;">Your teaching resource is now available to download from your dashboard. Simply log in to your account and navigate to the 'My Resources' section to access it at any time.</p>
                                        
                                        <!-- Payment and Billing Details -->
                                        <table width="100%" cellpadding="0" cellspacing="0" style="margin-top: 40px;">
                                            <tr>
                                                <td style="width: 48%; vertical-align: top; padding-right: 2%;">
                                                    <div style="font-size: 14px; font-weight: 600; color: #333; margin-bottom: 10px;">Payment details</div>
                                                    <div style="font-size: 14px; color: #666; line-height: 1.6;">
                                                        Card: {card_brand if card_brand else 'N/A'}<br>
                                                        Card# ending: •••• {payment_method_display.split()[-1] if 'ending' in payment_method_display else '****'}
                                                    </div>
                                                </td>
                                                <td style="width: 48%; vertical-align: top; padding-left: 2%;">
                                                    <div style="font-size: 14px; font-weight: 600; color: #333; margin-bottom: 10px;">Billing details</div>
                                                    <div style="font-size: 14px; color: #666; line-height: 1.6;">
                                                        {customer_name}<br>
                                                        {billing_address_formatted if billing_address_formatted else 'No billing address provided'}
                                                    </div>
                                                </td>
                                            </tr>
                                        </table>
                                        
                                        <!-- Footer Message -->
                                        <div style="margin-top: 50px; padding-top: 30px; border-top: 1px solid #e0e0e0;">
                                            <p style="font-size: 14px; color: #666; line-height: 1.6; margin: 0;">
                                                Best wishes<br>
                                                <p style="color: #333;">The Learnogic team<br>cultivating excellence</p>
                                            </p>
                                        </div>
                                        
                                    </td>
                                </tr>
                                
                                <!-- Copyright Footer -->
                                <tr>
                                    <td style="padding: 20px 40px; background-color: #f9f9f9; text-align: center; border-top: 1px solid #e0e0e0;">
                                        <p style="font-size: 12px; color: #999; margin: 0;">© Learnogic 2025 • All rights reserved.</p>
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
        
        email_response = ses_service.send_email(order_email)
        logger.info(f"Order confirmation email sent to {customer_email}. Order ID: {new_purchase.id}, MessageId: {email_response.message_id}")
        
    except Exception as email_error:
        logger.error(f"Failed to send order confirmation email for order {new_purchase.id} to {customer_email}: {str(email_error)}")
    
    return new_purchase

# Get all purchases for the current user
@router.get("/", response_model=List[PurchaseResponse])
def get_all_purchases(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    purchases = db.query(Purchase).filter(Purchase.user_id == current_user.id).all()
    
    # Load details for each purchase
    result = []
    for purchase in purchases:
        purchase_dict = {
            "id": purchase.id,
            "user_id": purchase.user_id,
            "total_amount": purchase.total_amount,
            "transaction_id": purchase.transaction_id,
            "payment_method": purchase.payment_method,
            "status": purchase.status,
            "created_at": purchase.created_at,
            "purchase_items": []
        }
        
        # Load items for each purchase
        for item in purchase.purchase_items:
            item_dict = {
                "id": item.id,
                "item_type": item.item_type,
                "theme_id": item.theme_id,
                "resource_id": item.resource_id,
                "quantity": item.quantity,
                "event_id": item.event_id,
                "price": item.price,
                "resource": None,
                "theme": None,
                "event": None
            }
            
            # Load resource and theme details
            if item.item_type == "resource" and item.resource_id:
                resource = db.query(Resources).filter(Resources.id == item.resource_id).first()
                if resource:
                    item_dict["resource"] = {
                        "id": resource.id,
                        "name": resource.name
                    }
                
                if item.theme_id:
                    theme = db.query(Theme).filter(Theme.id == item.theme_id).first()
                    if theme:
                        item_dict["theme"] = {
                            "id": theme.id,
                            "name": theme.name,
                            "price": theme.price,
                            "data" : theme.data
                        }
            
            # Load event details
            elif item.item_type == "event" and item.event_id:
                event = db.query(Event).filter(Event.id == item.event_id).first()
                if event:
                    item_dict["event"] = {
                        "id": event.id,
                        "name": event.title,
                        "price": event.price,
                        "time" : event.time,
                        "location" : event.location,
                        "date" : event.date_day+'-'+event.date_month+'-'+event.date_year
                    }
            
            purchase_dict["purchase_items"].append(item_dict)
        
        result.append(purchase_dict)
    
    return result

# Get a specific purchase by ID
@router.get("/{purchase_id}", response_model=PurchaseResponse)
def get_purchase(
    purchase_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    purchase = db.query(Purchase).filter(
        Purchase.id == purchase_id,
        Purchase.user_id == current_user.id
    ).first()
    
    if not purchase:
        raise HTTPException(status_code=404, detail="Purchase not found")
    
    return purchase

# Admin endpoint to get all purchases (limited by user permissions)
@router.get("/admin/all", response_model=List[PurchaseResponse])
def admin_get_all_purchases(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # Check if user is admin
    if current_user.user_type != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this resource"
        )
    
    purchases = db.query(Purchase).all()
    return purchases

# Update purchase status (admin only)
@router.patch("/{purchase_id}/status", response_model=PurchaseResponse)
def update_purchase_status(
    purchase_id: int,
    status: PurchaseStatus,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # Check if user is admin
    if current_user.user_type != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to perform this action"
        )
    
    purchase = db.query(Purchase).filter(Purchase.id == purchase_id).first()
    if not purchase:
        raise HTTPException(status_code=404, detail="Purchase not found")
    
    purchase.status = status
    db.commit()
    db.refresh(purchase)
    
    return purchase

# Delete a purchase (admin only)
@router.delete("/{purchase_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_purchase(
    purchase_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # Check if user is admin
    if current_user.user_type != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to perform this action"
        )
    
    purchase = db.query(Purchase).filter(Purchase.id == purchase_id).first()
    if not purchase:
        raise HTTPException(status_code=404, detail="Purchase not found")
    
    db.delete(purchase)
    db.commit()
    return