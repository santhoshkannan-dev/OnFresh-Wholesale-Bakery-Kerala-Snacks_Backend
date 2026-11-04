import uuid
from decimal import Decimal
from typing import Dict, Any, Tuple
from django.db import transaction
from django.core.exceptions import ValidationError
from .models import Order, Payment


class BasePaymentGateway:
    """Base class for payment providers."""

    def initiate_payment(self, order: Order, idempotency_key: str = None) -> Dict[str, Any]:
        raise NotImplementedError

    def verify_payment(self, order: Order, payload: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        raise NotImplementedError


class CODPaymentGateway(BasePaymentGateway):
    """
    Cash on Delivery payment provider.
    Payment is settled when customer receives order from delivery partner.
    """

    def initiate_payment(self, order: Order, idempotency_key: str = None) -> Dict[str, Any]:
        if not idempotency_key:
            idempotency_key = f"cod_{order.order_number}_{uuid.uuid4().hex[:8]}"

        with transaction.atomic():
            payment, created = Payment.objects.get_or_create(
                order=order,
                idempotency_key=idempotency_key,
                defaults={
                    'transaction_id': f"TXN-COD-{order.order_number}",
                    'payment_method': 'cod',
                    'amount': order.total_amount,
                    'status': 'pending',
                    'gateway_provider': 'cod',
                    'gateway_payload': {
                        'instructions': 'Pay cash or UPI to delivery agent upon receiving the package.'
                    }
                }
            )
            order.payment_method = 'cod'
            order.payment_status = 'pending'
            order.save(update_fields=['payment_method', 'payment_status', 'updated_at'])

        return {
            'status': 'success',
            'payment_method': 'cod',
            'transaction_id': payment.transaction_id,
            'amount': float(payment.amount),
            'order_number': order.order_number,
            'instructions': 'Cash on Delivery selected. Please keep exact change ready upon delivery.',
        }

    def verify_payment(self, order: Order, payload: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        return True, "Cash on delivery confirmed", {}


class BankTransferPaymentGateway(BasePaymentGateway):
    """
    Direct NEFT / RTGS / IMPS Bank Transfer provider.
    Essential for wholesale B2B business customers in Kerala.
    """

    BANK_DETAILS = {
        'account_name': 'OnFresh Foods & Bakers Private Limited',
        'bank_name': 'State Bank of India',
        'branch': 'Vandiperiyar Branch, Idukki, Kerala',
        'account_number': '39485720192',
        'account_type': 'Current Account',
        'ifsc_code': 'SBIN0070123',
        'upi_id': 'onfresh@sbi',
    }

    def initiate_payment(self, order: Order, idempotency_key: str = None) -> Dict[str, Any]:
        if not idempotency_key:
            idempotency_key = f"bank_{order.order_number}_{uuid.uuid4().hex[:8]}"

        with transaction.atomic():
            payment, _ = Payment.objects.get_or_create(
                order=order,
                idempotency_key=idempotency_key,
                defaults={
                    'transaction_id': f"TXN-NEFT-{order.order_number}",
                    'payment_method': 'bank_transfer',
                    'amount': order.total_amount,
                    'status': 'pending',
                    'gateway_provider': 'bank_transfer',
                    'gateway_payload': {
                        'bank_details': self.BANK_DETAILS,
                        'reference_note': f"Transfer Reference: {order.order_number}",
                    }
                }
            )
            order.payment_method = 'bank_transfer'
            order.payment_status = 'pending'
            order.save(update_fields=['payment_method', 'payment_status', 'updated_at'])

        return {
            'status': 'success',
            'payment_method': 'bank_transfer',
            'transaction_id': payment.transaction_id,
            'amount': float(payment.amount),
            'order_number': order.order_number,
            'bank_details': self.BANK_DETAILS,
            'instructions': f"Transfer ₹{order.total_amount} to OnFresh account quoting Order Number '{order.order_number}'.",
        }

    def verify_payment(self, order: Order, payload: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        ref = payload.get('utr_reference', '').strip()
        if not ref:
            return False, "UTR / Bank reference number is required.", {}

        with transaction.atomic():
            payment = order.payments.filter(payment_method='bank_transfer').first()
            if payment:
                payment.gateway_payload['utr_reference'] = ref
                payment.save(update_fields=['gateway_payload', 'updated_at'])

        return True, f"UTR reference {ref} recorded for verification.", {'utr_reference': ref}


class OnlinePaymentGatewayFoundation(BasePaymentGateway):
    """
    Provider-agnostic online payment foundation (Razorpay / Cashfree / UPI).
    Demonstrates idempotent signature verification and prevent duplicate settlement.
    """

    def initiate_payment(self, order: Order, idempotency_key: str = None) -> Dict[str, Any]:
        if not idempotency_key:
            idempotency_key = f"online_{order.order_number}_{uuid.uuid4().hex[:8]}"

        # Prevent duplicate payment initiation if already paid
        if order.payment_status == 'paid':
            raise ValidationError("Order has already been paid.")

        with transaction.atomic():
            payment, created = Payment.objects.get_or_create(
                order=order,
                idempotency_key=idempotency_key,
                defaults={
                    'transaction_id': f"TXN-ONL-{order.order_number}-{uuid.uuid4().hex[:6].upper()}",
                    'payment_method': 'online',
                    'amount': order.total_amount,
                    'status': 'pending',
                    'gateway_provider': 'online_gateway_foundation',
                    'gateway_payload': {
                        'session_id': f"sess_{uuid.uuid4().hex}",
                        'currency': 'INR',
                    }
                }
            )
            order.payment_method = 'online'
            order.save(update_fields=['payment_method', 'updated_at'])

        return {
            'status': 'success',
            'payment_method': 'online',
            'transaction_id': payment.transaction_id,
            'idempotency_key': idempotency_key,
            'amount': float(payment.amount),
            'currency': 'INR',
            'order_number': order.order_number,
            'instructions': 'Online payment intent registered. Integrate live Razorpay/Cashfree merchant keys in production.',
        }

    def verify_payment(self, order: Order, payload: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        transaction_id = payload.get('transaction_id')
        payment = order.payments.filter(transaction_id=transaction_id).first()

        if not payment:
            return False, f"Payment transaction '{transaction_id}' not found.", {}

        if payment.status == 'successful':
            return True, "Payment was already verified successfully.", {}

        # Validate signature/response
        signature = payload.get('gateway_signature')
        # In testing/foundation mode: simulate verification
        is_valid = bool(signature and len(signature) >= 6)

        with transaction.atomic():
            if is_valid:
                payment.status = 'successful'
                payment.gateway_payload['verified_at'] = str(uuid.uuid4().hex)
                payment.save(update_fields=['status', 'gateway_payload', 'updated_at'])

                order.payment_status = 'paid'
                if order.order_status == 'pending':
                    order.order_status = 'confirmed'
                order.save(update_fields=['payment_status', 'order_status', 'updated_at'])
                return True, "Online payment verified successfully.", {'status': 'successful'}
            else:
                payment.status = 'failed'
                payment.save(update_fields=['status', 'updated_at'])
                order.payment_status = 'failed'
                order.save(update_fields=['payment_status', 'updated_at'])
                return False, "Invalid payment signature.", {'status': 'failed'}


def get_payment_gateway(method: str) -> BasePaymentGateway:
    """Factory function for payment gateways."""
    if method == 'cod':
        return CODPaymentGateway()
    elif method == 'bank_transfer':
        return BankTransferPaymentGateway()
    elif method == 'online':
        return OnlinePaymentGatewayFoundation()
    else:
        raise ValidationError(f"Unsupported payment method: {method}")

