# app/services/purchase_service.py - Add these methods to your existing PurchaseService

import json
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from decimal import Decimal
import uuid
import logging

from app.models import User, Purchase, PurchaseItem
from app.schemas import CartItem
from app.core.exceptions import ValidationException, NotFoundException
from ..utils.ses import SESService

logger = logging.getLogger(__name__)
ses_service = SESService()

class PurchaseService:
    
    @staticmethod
    async def create_purchase_from_payment(
        db: Session,
        user: User,
        payment_result: Dict[str, Any],
        billing_address: Optional[Dict] = None,
        cart_items: Optional[List[CartItem]] = None
    ) -> Purchase:
        """
        Create a purchase record from successful Stripe payment
        """
        try:
            # Create purchase record
            payment_intent_id = payment_result['payment_intent_id']
            custom_transaction_id = payment_intent_id.replace('pi_', 'lgc_pi_')
            
            # Extract payment method information
            payment_method_info = payment_result.get('payment_method_details')
            payment_method_display = 'stripe_card'

            if payment_method_info:
                if payment_method_info['type'] == 'card':
                    brand = payment_method_info.get('brand', 'card').capitalize()
                    last4 = payment_method_info.get('last4', '')
                    payment_method_display = f"{brand} ending in {last4}"

            purchase = Purchase(
                user_id=user.id,  # Fixed: was user.user_id
                total_amount=Decimal(str(payment_result['amount'])),
                status='completed',
                payment_method=payment_method_display,  # Store formatted payment method
                payment_status='succeeded',
                transaction_id=custom_transaction_id,  # Use custom transaction ID
                payment_intent_id=payment_result['payment_intent_id'],
                payment_method_id=payment_result.get('payment_method_id'),
                stripe_charge_id=payment_result.get('charges', [{}])[0].get('id') if payment_result.get('charges') else None,
                payment_metadata=json.dumps(payment_result),
                billing_address=json.dumps(billing_address) if billing_address else None
            )
            
            db.add(purchase)
            db.flush()  # Get the purchase ID without committing
            
            # If you have cart items, create purchase items
            if cart_items:
                for cart_item in cart_items:
                    purchase_item = PurchaseItem(
                        purchase_id=purchase.purchase_id,
                        item_id=cart_item.item_id,
                        item_type=cart_item.item_type,
                        item_name=cart_item.name,
                        quantity=cart_item.quantity,
                        unit_price=cart_item.price,
                        total_price=cart_item.price * cart_item.quantity
                    )
                    db.add(purchase_item)
            
            db.commit()
            db.refresh(purchase)
            
            # Send confirmation email
            # try:
            #     await EmailService.send_purchase_confirmation(
            #         user=user,
            #         purchase=purchase,
            #         billing_address=billing_address
            #     )
            #     logger.info(f"Sent purchase confirmation email for purchase {purchase.purchase_id}")
            # except Exception as e:
            #     logger.error(f"Failed to send purchase confirmation email: {str(e)}")
                # Don't fail the purchase if email fails
            
            logger.info(f"Created purchase {purchase.purchase_id} from payment {payment_result['payment_intent_id']}")
            return purchase
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create purchase from payment: {str(e)}")
            raise ValidationException("Failed to complete purchase")
    
    @staticmethod
    async def get_purchase_by_payment_intent(
        db: Session,
        payment_intent_id: str
    ) -> Optional[Purchase]:
        """
        Get purchase by Stripe payment intent ID
        """
        return db.query(Purchase).filter(
            Purchase.payment_intent_id == payment_intent_id
        ).first()
    
    @staticmethod
    async def update_payment_status(
        db: Session,
        purchase_id: uuid.UUID,
        payment_status: str,
        payment_metadata: Optional[Dict] = None
    ) -> bool:
        """
        Update payment status for a purchase
        """
        try:
            purchase = db.query(Purchase).filter(
                Purchase.purchase_id == purchase_id
            ).first()
            
            if not purchase:
                raise NotFoundException("Purchase not found")
            
            purchase.payment_status = payment_status
            
            if payment_metadata:
                existing_metadata = {}
                if purchase.payment_metadata:
                    try:
                        existing_metadata = json.loads(purchase.payment_metadata)
                    except json.JSONDecodeError:
                        pass
                
                existing_metadata.update(payment_metadata)
                purchase.payment_metadata = json.dumps(existing_metadata)
            
            # Update purchase status based on payment status
            if payment_status == 'succeeded':
                purchase.status = 'completed'
            elif payment_status == 'failed':
                purchase.status = 'cancelled'
            
            db.commit()
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update payment status: {str(e)}")
            return False