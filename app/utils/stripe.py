# app/services/stripe_service.py
import stripe
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from decimal import Decimal
import uuid
import logging

from app.models import User, Purchase, PurchaseItem, TutorProfile
from app.config import settings
from app.core.exceptions import PaymentException, NotFoundException, ValidationException

logger = logging.getLogger(__name__)

# Configure Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY


class StripeService:
    
    # Supported currencies with their display info
    SUPPORTED_CURRENCIES = {
        'gbp': {'symbol': '£', 'name': 'British Pound', 'primary': True},
        'usd': {'symbol': '$', 'name': 'US Dollar', 'primary': False},
        'eur': {'symbol': '€', 'name': 'Euro', 'primary': False},
        'inr': {'symbol': '₹', 'name': 'Indian Rupee', 'primary': False}
    }
    
    DEFAULT_CURRENCY = 'gbp'
    
    @staticmethod
    async def get_or_create_customer(db: Session, user: User) -> str:
        """
        Get existing Stripe customer or create a new one
        """
        try:
            # Check if user already has a Stripe customer ID
            if user.stripe_customer_id:
                try:
                    # Verify the customer still exists in Stripe
                    customer = stripe.Customer.retrieve(user.stripe_customer_id)
                    return customer.id
                except stripe.error.InvalidRequestError:
                    # Customer doesn't exist, create a new one
                    logger.warning(f"Stripe customer {user.stripe_customer_id} not found, creating new one")
                    user.stripe_customer_id = None
            
            # Create new Stripe customer
            customer_data = {
                'email': user.email,
                'name': user.full_name,
                'metadata': {
                    'user_id': str(user.id),
                    'username': user.email
                }
            }
            
            customer = stripe.Customer.create(**customer_data)
            
            # Save customer ID to user record
            user.stripe_customer_id = customer.id
            db.commit()
            
            logger.info(f"Created Stripe customer {customer.id} for user {user.id}")
            return customer.id
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error creating customer: {str(e)}")
            raise PaymentException(f"Failed to create payment customer: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error creating Stripe customer: {str(e)}")
            raise PaymentException("Failed to create payment customer")
    
    @staticmethod
    async def create_payment_intent(
        db: Session,
        user: User,
        amount: Decimal,
        currency: str = DEFAULT_CURRENCY,
        cart_items: List[Dict] = None,
        billing_address: Optional[Dict] = None,
        save_payment_method: bool = True
    ) -> Dict[str, Any]:
        """
        Create a Stripe Payment Intent for checkout
        """
        try:
            # Validate currency
            currency = currency.lower()
            if currency not in StripeService.SUPPORTED_CURRENCIES:
                raise ValidationException(f"Currency {currency} is not supported")
            
            # Convert amount to smallest currency unit (pence, cents, etc.)
            stripe_amount = int(amount * 100)
            
            if stripe_amount == 0:
                logger.info(f"Free order for user {user.id}, skipping payment intent creation")
                return {
                    'payment_intent_id': None,
                    'client_secret': None,
                    'customer_id': None,
                    'amount': amount,
                    'currency': currency,
                    'status': 'free_order'
                }
            
            if stripe_amount < 50:  # Stripe minimum (£0.50)
                raise ValidationException("Minimum payment amount is £0.50")
            
            # Get or create Stripe customer
            customer_id = await StripeService.get_or_create_customer(db, user)
            
            # Prepare metadata
            metadata = {
                'user_id': str(user.id),
                'currency_display': currency.upper(),
                'custom_prefix': 'lgc',
            }
            
            # Add cart items to metadata (limited by Stripe's 500 char per key limit)
            if cart_items:
                metadata['cart_items_count'] = str(len(cart_items))
                for i, item in enumerate(cart_items[:5]):  # Limit to first 5 items
                    item_key = f"item_{i}"
                    item_value = f"{item.get('name', 'Unknown')} x{item.get('quantity', 1)}"
                    metadata[item_key] = item_value[:500]  # Stripe metadata value limit
            
            # Payment Intent configuration
            intent_data = {
                'amount': stripe_amount,
                'currency': currency,
                'customer': customer_id,
                'metadata': metadata,
                'automatic_payment_methods': {'enabled': True},
                # Remove confirmation_method and confirm when using automatic_payment_methods
            }
            
            # Configure payment method saving
            if save_payment_method:
                intent_data['setup_future_usage'] = 'on_session'
            
            # Add billing address if provided
            if billing_address:
                intent_data['shipping'] = {
                    'name': user.full_name,
                    'address': {
                        'line1': billing_address.get('line1', ''),
                        'line2': billing_address.get('line2', ''),
                        'city': billing_address.get('city', ''),
                        'postal_code': billing_address.get('postal_code', ''),
                        'country': billing_address.get('country', 'GB'),
                        'state': billing_address.get('state', ''),
                    }
                }
            
            # Create Payment Intent
            intent = stripe.PaymentIntent.create(**intent_data)
            
            logger.info(f"Created Payment Intent {intent.id} for user {user.id}")
            
            return {
                'payment_intent_id': intent.id,
                'client_secret': intent.client_secret,
                'customer_id': customer_id,
                'amount': amount,
                'currency': currency,
                'status': intent.status
            }
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error creating payment intent: {str(e)}")
            raise PaymentException(f"Failed to create payment intent: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error creating payment intent: {str(e)}")
            raise PaymentException("Failed to create payment intent")
    
    @staticmethod
    async def confirm_payment_intent(payment_intent_id: str) -> Dict[str, Any]:
        """
        Confirm a Payment Intent and return payment details
        """
        try:
            intent = stripe.PaymentIntent.retrieve(payment_intent_id, expand=['payment_method'])
            
            if intent.status == 'succeeded':
                # Extract payment method details
                payment_method_details = None
                if intent.payment_method and hasattr(intent.payment_method, 'card'):
                    payment_method_details = {
                        'type': 'card',
                        'brand': intent.payment_method.card.brand,
                        'last4': intent.payment_method.card.last4,
                        'exp_month': intent.payment_method.card.exp_month,
                        'exp_year': intent.payment_method.card.exp_year
                    }
                elif intent.charges and intent.charges.data:
                    # Fallback to charges data if payment_method not expanded
                    charge = intent.charges.data[0]
                    if charge.payment_method_details:
                        pm_details = charge.payment_method_details
                        if pm_details.type == 'card':
                            payment_method_details = {
                                'type': 'card',
                                'brand': pm_details.card.brand,
                                'last4': pm_details.card.last4,
                                'exp_month': pm_details.card.exp_month,
                                'exp_year': pm_details.card.exp_year
                            }
                
                return {
                    'success': True,
                    'payment_intent_id': intent.id,
                    'amount': intent.amount / 100,
                    'currency': intent.currency,
                    'payment_method_id': intent.payment_method,
                    'payment_method_details': payment_method_details,  # Add this
                    'customer_id': intent.customer,
                    'charges': intent.charges.data if intent.charges else []
                }
                
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error confirming payment: {str(e)}")
            raise PaymentException(f"Failed to confirm payment: {str(e)}")
    
    @staticmethod
    async def get_customer_payment_methods(customer_id: str) -> List[Dict]:
        """
        Get saved payment methods for a customer
        """
        try:
            payment_methods = stripe.PaymentMethod.list(
                customer=customer_id,
                type='card'
            )
            
            methods = []
            for pm in payment_methods.data:
                card = pm.card
                methods.append({
                    'id': pm.id,
                    'brand': card.brand,
                    'last4': card.last4,
                    'exp_month': card.exp_month,
                    'exp_year': card.exp_year,
                    'country': card.country,
                    'is_default': False  # You might want to implement a default payment method logic
                })
            
            return methods
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error getting payment methods: {str(e)}")
            raise PaymentException(f"Failed to get payment methods: {str(e)}")
    
    @staticmethod
    async def create_payment_intent_with_saved_method(
        db: Session,
        user: User,
        payment_method_id: str,
        amount: Decimal,
        currency: str = DEFAULT_CURRENCY
    ) -> Dict[str, Any]:
        """
        Create Payment Intent using a saved payment method
        """
        try:
            customer_id = await StripeService.get_or_create_customer(db, user)
            stripe_amount = int(amount * 100)
            
            intent = stripe.PaymentIntent.create(
                amount=stripe_amount,
                currency=currency,
                customer=customer_id,
                payment_method=payment_method_id,
                confirm=True,
                return_url=f"{settings.STRIPE_SUCCESS_URL}",  # Add this to your settings
                metadata={
                    'user_id': str(user.id),
                    'payment_type': 'saved_method'
                }
            )
            
            return {
                'payment_intent_id': intent.id,
                'status': intent.status,
                'amount': amount,
                'currency': currency
            }
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error with saved payment method: {str(e)}")
            raise PaymentException(f"Payment failed: {str(e)}")
    
    @staticmethod
    async def handle_webhook_event(event_data: Dict, db: Session = None) -> bool:
        """
        Handle Stripe webhook events
        """
        try:
            event_type = event_data.get('type')
            
            if event_type == 'payment_intent.succeeded':
                intent = event_data['data']['object']
                logger.info(f"Payment succeeded for intent {intent['id']}")
                # Additional success handling can be added here
                
            elif event_type == 'payment_intent.payment_failed':
                intent = event_data['data']['object']
                logger.warning(f"Payment failed for intent {intent['id']}")
                # Additional failure handling can be added here
                
            elif event_type == 'checkout.session.completed':
                session = event_data['data']['object']
                if session.get('mode') == 'subscription':
                    metadata = session.get('metadata', {})
                    user_id = metadata.get('user_id')
                    sub_type = metadata.get('type')
                    if sub_type == 'tutor_subscription' and user_id and db:
                        logger.info(f"Tutor subscription completed for user {user_id}")
                        tutor = db.query(TutorProfile).filter(TutorProfile.user_id == int(user_id)).first()
                        if tutor:
                            tutor.is_subscribed = True
                            tutor.stripe_subscription_id = session.get('subscription')
                            db.commit()

            elif event_type == 'customer.subscription.deleted' or event_type == 'customer.subscription.canceled':
                subscription = event_data['data']['object']
                sub_id = subscription.get('id')
                if db and sub_id:
                    logger.info(f"Subscription canceled: {sub_id}")
                    tutor = db.query(TutorProfile).filter(TutorProfile.stripe_subscription_id == sub_id).first()
                    if tutor:
                        tutor.is_subscribed = False
                        tutor.stripe_subscription_id = None
                        db.commit()

            return True
            
        except Exception as e:
            logger.error(f"Error handling webhook: {str(e)}")
            return False

    @staticmethod
    async def create_tutor_subscription_checkout(
        db: Session,
        user: User,
        success_url: str,
        cancel_url: str
    ) -> str:
        """
        Create a Checkout Session for £25/month tutor subscription
        """
        try:
            customer_id = await StripeService.get_or_create_customer(db, user)
            
            session = stripe.checkout.Session.create(
                customer=customer_id,
                payment_method_types=['card'],
                line_items=[{
                    'price_data': {
                        'currency': 'gbp',
                        'product_data': {
                            'name': 'Tutor Subscription (£25/month)',
                            'description': 'Monthly subscription to appear in the public tutor search.',
                        },
                        'unit_amount': 2500, # £25.00
                        'recurring': {
                            'interval': 'month',
                        },
                    },
                    'quantity': 1,
                }],
                mode='subscription',
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={
                    'user_id': str(user.id),
                    'type': 'tutor_subscription'
                },
                subscription_data={
                    'metadata': {
                        'user_id': str(user.id),
                        'type': 'tutor_subscription'
                    }
                }
            )
            return session.url
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error creating subscription checkout: {str(e)}")
            raise PaymentException(f"Failed to create subscription checkout: {str(e)}")

    @staticmethod
    async def cancel_subscription(subscription_id: str) -> bool:
        """
        Cancel an active Stripe subscription
        """
        if subscription_id == 'sub_manual':
            return True
            
        try:
            stripe.Subscription.delete(subscription_id)
            return True
        except stripe.error.InvalidRequestError as e:
            if "No such subscription" in str(e):
                logger.warning(f"Subscription {subscription_id} already deleted in Stripe.")
                return True
            logger.error(f"Stripe invalid request error cancelling subscription: {str(e)}")
            raise PaymentException(f"Failed to cancel subscription: {str(e)}")
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error cancelling subscription: {str(e)}")
            raise PaymentException(f"Failed to cancel subscription: {str(e)}")

    @staticmethod
    async def verify_tutor_subscription(db: Session, session_id: str) -> bool:
        """
        Manually verify a checkout session and update the DB if the webhook was missed
        """
        try:
            session = stripe.checkout.Session.retrieve(session_id)
            if session.status == 'complete' and session.mode == 'subscription':
                metadata = session.get('metadata', {})
                user_id = metadata.get('user_id')
                if user_id:
                    tutor = db.query(TutorProfile).filter(TutorProfile.user_id == int(user_id)).first()
                    if tutor and not tutor.is_subscribed:
                        logger.info(f"Manual verification: Tutor subscription completed for user {user_id}")
                        tutor.is_subscribed = True
                        tutor.stripe_subscription_id = session.get('subscription')
                        db.commit()
                        return True
            return False
        except Exception as e:
            logger.error(f"Error verifying subscription: {str(e)}")
            return False
    
    @staticmethod
    def get_supported_currencies() -> Dict[str, Dict]:
        """
        Get list of supported currencies
        """
        return StripeService.SUPPORTED_CURRENCIES
    
    @staticmethod
    def format_amount(amount: Decimal, currency: str) -> str:
        """
        Format amount with currency symbol
        """
        currency = currency.lower()
        currency_info = StripeService.SUPPORTED_CURRENCIES.get(currency, {'symbol': currency.upper()})
        symbol = currency_info.get('symbol', currency.upper())
        
        if currency == 'inr':
            # Indian Rupee typically shown with symbol after amount
            return f"{amount:.2f} {symbol}"
        else:
            return f"{symbol}{amount:.2f}"