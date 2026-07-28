# app/routes/stripe_routes.py
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.orm import Session
from typing import Optional
import json
import stripe
import logging

from app.auth import get_current_user

from app.database import get_db
from app.models import User, TutorProfile
from app.schemas import (
    CreatePaymentIntentRequest,
    PaymentIntentResponse,
    ConfirmPaymentRequest,
    PaymentConfirmationResponse,
    PaymentMethodsResponse,
    PaymentWithSavedMethodRequest,
    StripeWebhookEvent,
    SupportedCurrenciesResponse,
    CurrencyInfo,
    TutorSubscriptionCheckoutRequest,
    TutorSubscriptionCheckoutResponse,
    TutorSubscriptionCancelResponse,
    TutorSubscriptionDetailsResponse
)
from app.utils.stripe import StripeService
from app.utils.purchase_service import PurchaseService  # Assuming you have this
from app.core.exceptions import PaymentException, ValidationException
from app.config import settings

router = APIRouter(prefix="/api/stripe", tags=["Stripe Payment"])
logger = logging.getLogger(__name__)


@router.post("/create-payment-intent", response_model=PaymentIntentResponse)
async def create_payment_intent(
    request: CreatePaymentIntentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a Stripe Payment Intent for checkout
    """
    try:
        # Convert cart items to dict format
        cart_items = [item.dict() for item in request.cart_items]
        
        # Convert billing address if provided
        billing_address = request.billing_address.dict() if request.billing_address else None
        
        # Check if total amount is 0 (all free items)
        if request.amount == 0:
            logger.info(f"Free order for user {current_user.id}")
            return PaymentIntentResponse(
                payment_intent_id=None,
                client_secret=None,
                customer_id=None,
                amount=0,
                currency=request.currency,
                status='free_order'
            )
        
        payment_intent = await StripeService.create_payment_intent(
            db=db,
            user=current_user,
            amount=request.amount,
            currency=request.currency,
            cart_items=cart_items,
            billing_address=billing_address,
            save_payment_method=request.save_payment_method
        )
        
        return PaymentIntentResponse(**payment_intent)
        
    except (PaymentException, ValidationException) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error creating payment intent: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
    

@router.post("/confirm-payment", response_model=PaymentConfirmationResponse)
async def confirm_payment(
    request: ConfirmPaymentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Confirm payment and complete the purchase
    """
    try:
        # Confirm the payment intent with Stripe
        payment_result = await StripeService.confirm_payment_intent(request.payment_intent_id)
        
        if not payment_result['success']:
            return PaymentConfirmationResponse(
                success=False,
                payment_intent_id=request.payment_intent_id,
                amount=0,
                currency="gbp",
                message="Payment failed or was not completed"
            )
        
        # Create the purchase record (you'll need to implement this based on your existing logic)
        try:
            purchase = await PurchaseService.create_purchase_from_payment(
                db=db,
                user=current_user,
                payment_result=payment_result,
                billing_address=request.billing_address.dict() if request.billing_address else None
            )
            
            return PaymentConfirmationResponse(
                success=True,
                payment_intent_id=request.payment_intent_id,
                purchase_id=purchase.purchase_id,
                amount=payment_result['amount'],
                currency=payment_result['currency'],
                message="Payment successful and purchase completed",
                payment_method={
                    'payment_method_id': payment_result.get('payment_method_id'),
                    'customer_id': payment_result.get('customer_id')
                }
            )
            
        except Exception as e:
            logger.error(f"Payment succeeded but purchase creation failed: {str(e)}")
            # Payment succeeded but purchase creation failed
            # You might want to handle this case differently
            raise HTTPException(
                status_code=500, 
                detail="Payment was processed but order completion failed. Please contact support."
            )
            
    except PaymentException as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error confirming payment: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/payment-methods", response_model=PaymentMethodsResponse)
async def get_payment_methods(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get user's saved payment methods
    """
    try:
        if not current_user.stripe_customer_id:
            return PaymentMethodsResponse(payment_methods=[], default_method_id=None)
        
        payment_methods = await StripeService.get_customer_payment_methods(
            current_user.stripe_customer_id
        )
        
        return PaymentMethodsResponse(
            payment_methods=payment_methods,
            default_method_id=payment_methods[0]['id'] if payment_methods else None
        )
        
    except PaymentException as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting payment methods: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/pay-with-saved-method", response_model=PaymentConfirmationResponse)
async def pay_with_saved_method(
    request: PaymentWithSavedMethodRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Process payment using a saved payment method
    """
    try:
        payment_result = await StripeService.create_payment_intent_with_saved_method(
            db=db,
            user=current_user,
            payment_method_id=request.payment_method_id,
            amount=request.amount,
            currency=request.currency
        )
        
        if payment_result['status'] == 'succeeded':
            # Create purchase record
            purchase = await PurchaseService.create_purchase_from_payment(
                db=db,
                user=current_user,
                payment_result=payment_result,
                billing_address=request.billing_address.dict() if request.billing_address else None
            )
            
            return PaymentConfirmationResponse(
                success=True,
                payment_intent_id=payment_result['payment_intent_id'],
                purchase_id=purchase.purchase_id,
                amount=request.amount,
                currency=request.currency,
                message="Payment successful"
            )
        else:
            return PaymentConfirmationResponse(
                success=False,
                payment_intent_id=payment_result['payment_intent_id'],
                amount=request.amount,
                currency=request.currency,
                message="Payment failed"
            )
            
    except PaymentException as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error processing saved payment method: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/supported-currencies", response_model=SupportedCurrenciesResponse)
async def get_supported_currencies():
    """
    Get list of supported currencies
    """
    currencies = StripeService.get_supported_currencies()
    
    currency_list = []
    for code, info in currencies.items():
        currency_list.append(CurrencyInfo(
            code=code.upper(),
            symbol=info['symbol'],
            name=info['name'],
            is_primary=info['primary']
        ))
    
    return SupportedCurrenciesResponse(
        currencies=currency_list,
        default_currency=StripeService.DEFAULT_CURRENCY.upper()
    )


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(alias="stripe-signature"),
    db: Session = Depends(get_db)
):
    """
    Handle Stripe webhook events
    """
    try:
        payload = await request.body()
        
        # Verify webhook signature
        try:
            event = stripe.Webhook.construct_event(
                payload, stripe_signature, settings.STRIPE_WEBHOOK_SECRET
            )
        except ValueError as e:
            logger.error(f"Invalid payload in webhook: {str(e)}")
            raise HTTPException(status_code=400, detail="Invalid payload")
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Invalid signature in webhook: {str(e)}")
            raise HTTPException(status_code=400, detail="Invalid signature")
        
        # Handle the event
        success = await StripeService.handle_webhook_event(event, db)
        
        if success:
            return {"status": "success"}
        else:
            raise HTTPException(status_code=500, detail="Webhook processing failed")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in webhook: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/tutor-subscription/checkout", response_model=TutorSubscriptionCheckoutResponse)
async def create_tutor_subscription_checkout(
    request: TutorSubscriptionCheckoutRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate a Stripe Checkout URL for a £25/month Tutor subscription.
    """
    if current_user.user_type != "tutor":
        raise HTTPException(status_code=403, detail="Only tutors can subscribe.")
        
    try:
        url = await StripeService.create_tutor_subscription_checkout(
            db=db,
            user=current_user,
            success_url=request.success_url,
            cancel_url=request.cancel_url
        )
        return TutorSubscriptionCheckoutResponse(url=url)
    except Exception as e:
        logger.error(f"Error creating tutor subscription checkout: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/tutor-subscription/cancel", response_model=TutorSubscriptionCancelResponse)
async def cancel_tutor_subscription(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Cancel an active tutor subscription.
    """
    if current_user.user_type != "tutor":
        raise HTTPException(status_code=403, detail="Only tutors can manage subscriptions.")
        
    tutor = db.query(TutorProfile).filter(TutorProfile.user_id == current_user.id).first()
    if not tutor or not tutor.stripe_subscription_id:
        raise HTTPException(status_code=400, detail="No active subscription found.")
        
    try:
        await StripeService.cancel_subscription(tutor.stripe_subscription_id)
        
        # We can proactively set it here, or wait for webhook. Better to set it here so it's instant.
        tutor.is_subscribed = False
        tutor.stripe_subscription_id = None
        db.commit()
        
        return TutorSubscriptionCancelResponse(
            success=True,
            message="Subscription cancelled successfully."
        )
    except Exception as e:
        logger.error(f"Error cancelling tutor subscription: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tutor-subscription/verify")
async def verify_tutor_subscription(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Manually verify a checkout session for fallback syncing when webhooks fail
    """
    try:
        success = await StripeService.verify_tutor_subscription(db, session_id)
        return {"success": success}
    except Exception as e:
        logger.error(f"Error verifying subscription: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tutor-subscription/details", response_model=TutorSubscriptionDetailsResponse)
async def get_tutor_subscription_details(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get subscription billing details: when the tutor subscribed and when the next billing date is.
    """
    if current_user.user_type != "tutor":
        raise HTTPException(status_code=403, detail="Only tutors can view subscription details.")

    tutor = db.query(TutorProfile).filter(TutorProfile.user_id == current_user.id).first()
    if not tutor:
        raise HTTPException(status_code=404, detail="Tutor profile not found.")

    # Backfill subscribed_at for existing subscribers who pre-date this column
    if tutor.is_subscribed and not tutor.subscribed_at:
        from datetime import datetime, timezone
        # Use created_at as best approximation if no better info available
        tutor.subscribed_at = tutor.created_at or datetime.now(timezone.utc)
        db.commit()

    try:
        details = await StripeService.get_subscription_details(db, tutor)
        return TutorSubscriptionDetailsResponse(**details)
    except Exception as e:
        logger.error(f"Error fetching subscription details: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))