from decimal import Decimal
from typing import List, Dict, Any, Optional
from django.core.exceptions import ValidationError
from apps.products.models import ProductVariant


# Configurable delivery fee rules
RETAIL_DELIVERY_FEE = Decimal('50.00')
RETAIL_FREE_DELIVERY_THRESHOLD = Decimal('500.00')

WHOLESALE_DELIVERY_FEE = Decimal('200.00')
WHOLESALE_FREE_DELIVERY_THRESHOLD = Decimal('5000.00')


class PricingService:
    """
    Authoritative pricing and delivery calculation engine for OnFresh.
    Evaluates pricing tiers, wholesale approval, custom pricing, and delivery thresholds.
    Never trusts client-supplied prices.
    """

    @classmethod
    def calculate_delivery_charge(cls, subtotal: Decimal, is_wholesale: bool) -> Decimal:
        """
        Calculate delivery fee based on customer segment and order value.
        Retail: ₹50 delivery fee; FREE on orders ₹500 or more.
        Wholesale: ₹200 delivery/freight; FREE on orders ₹5,000 or more.
        """
        if is_wholesale:
            if subtotal >= WHOLESALE_FREE_DELIVERY_THRESHOLD:
                return Decimal('0.00')
            return WHOLESALE_DELIVERY_FEE
        else:
            if subtotal >= RETAIL_FREE_DELIVERY_THRESHOLD:
                return Decimal('0.00')
            return RETAIL_DELIVERY_FEE

    @classmethod
    def evaluate_line_item(
        cls,
        variant: ProductVariant,
        quantity: int,
        customer_profile: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Calculates pricing and checks constraints for a single variant line.
        """
        if quantity < 1:
            raise ValidationError(f"Quantity for {variant.sku} must be at least 1.")

        is_wholesale = bool(customer_profile and customer_profile.is_wholesale_approved)
        errors = []

        # 1. Availability validation
        if not variant.is_available:
            errors.append(f"{variant.product.name} ({variant.display_weight}) is currently unavailable.")

        if is_wholesale and not variant.is_available_wholesale:
            errors.append(f"{variant.product.name} ({variant.display_weight}) is not available for wholesale.")

        if not is_wholesale and not variant.is_available_retail:
            errors.append(f"{variant.product.name} ({variant.display_weight}) is not available for retail.")

        # 2. MOQ validation
        moq = variant.get_moq_for_customer(customer_profile)
        moq_met = quantity >= moq
        if not moq_met:
            errors.append(
                f"{variant.product.name} ({variant.display_weight}): Minimum order quantity is {moq} units. Provided: {quantity}."
            )

        # 3. Price resolution hierarchy
        # Conflict resolution order:
        # A. Approved wholesale:
        #    1. Active CustomerSpecialPrice
        #    2. Highest qualifying QuantityPriceTier (min_quantity <= quantity)
        #    3. Base wholesale price (effective_wholesale_price)
        # B. Retail:
        #    Standard retail price (MRP)
        retail_unit_price = Decimal(str(variant.price))
        rule_applied = "Standard Retail Price"

        if is_wholesale:
            special = variant.customer_special_prices.filter(
                customer=customer_profile,
                is_active=True
            ).first()

            if special:
                unit_price = Decimal(str(special.special_price))
                rule_applied = "Custom Negotiated Wholesale Price"
            else:
                tier = variant.price_tiers.filter(
                    min_quantity__lte=quantity
                ).order_by('-min_quantity').first()

                if tier:
                    unit_price = Decimal(str(tier.price_per_unit))
                    rule_applied = f"Wholesale Volume Tier ({tier.min_quantity}+ units)"
                else:
                    unit_price = Decimal(str(variant.effective_wholesale_price))
                    rule_applied = "Approved Wholesale Base Price"
        else:
            unit_price = retail_unit_price

        line_subtotal = retail_unit_price * quantity
        line_total = unit_price * quantity
        line_discount = line_subtotal - line_total if line_subtotal > line_total else Decimal('0.00')

        return {
            'variant': variant,
            'variant_id': variant.id,
            'sku': variant.sku,
            'product_name': variant.product.name,
            'package_weight': variant.package_weight,
            'package_unit': variant.package_unit,
            'display_weight': variant.display_weight,
            'image': variant.product.main_image.url if variant.product.main_image else None,
            'quantity': quantity,
            'moq': moq,
            'moq_met': moq_met,
            'retail_unit_price': retail_unit_price,
            'unit_price': unit_price,
            'line_subtotal': line_subtotal,
            'line_total': line_total,
            'line_discount': line_discount,
            'pricing_rule_applied': rule_applied,
            'errors': errors,
        }

    @classmethod
    def calculate_cart_pricing(
        cls,
        items_data: List[Dict[str, Any]],
        customer_profile: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Calculate authoritative pricing for a list of items: [{'variant_id': int, 'quantity': int}].
        """
        is_wholesale = bool(customer_profile and customer_profile.is_wholesale_approved)
        customer_segment = 'wholesale' if is_wholesale else 'retail'

        variant_ids = [item['variant_id'] for item in items_data]
        variants = ProductVariant.objects.filter(id__in=variant_ids).select_related('product').prefetch_related(
            'price_tiers',
            'customer_special_prices'
        )
        variant_map = {v.id: v for v in variants}

        evaluated_items = []
        all_errors = []
        subtotal = Decimal('0.00')
        total_discount = Decimal('0.00')

        for item in items_data:
            vid = item['variant_id']
            qty = int(item['quantity'])
            variant = variant_map.get(vid)

            if not variant:
                all_errors.append(f"Product variant ID {vid} not found.")
                continue

            evaluated = cls.evaluate_line_item(variant, qty, customer_profile)
            if evaluated['errors']:
                all_errors.extend(evaluated['errors'])

            evaluated_items.append(evaluated)
            subtotal += evaluated['line_total']
            total_discount += evaluated['line_discount']

        delivery_charge = cls.calculate_delivery_charge(subtotal, is_wholesale) if evaluated_items else Decimal('0.00')
        tax_amount = Decimal('0.00')  # Prices in Kerala are MRP / agreed wholesale rate inclusive of GST
        total_amount = subtotal + delivery_charge + tax_amount

        free_delivery_threshold = WHOLESALE_FREE_DELIVERY_THRESHOLD if is_wholesale else RETAIL_FREE_DELIVERY_THRESHOLD
        amount_for_free_delivery = max(Decimal('0.00'), free_delivery_threshold - subtotal)

        return {
            'is_valid': len(all_errors) == 0 and len(evaluated_items) > 0,
            'errors': all_errors,
            'customer_segment': customer_segment,
            'is_wholesale_approved': is_wholesale,
            'items': evaluated_items,
            'items_count': sum(item['quantity'] for item in evaluated_items),
            'subtotal': subtotal,
            'discount_amount': total_discount,
            'delivery_charge': delivery_charge,
            'tax_amount': tax_amount,
            'total_amount': total_amount,
            'free_delivery_threshold': free_delivery_threshold,
            'amount_for_free_delivery': amount_for_free_delivery,
            'currency': 'INR',
        }

