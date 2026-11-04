from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from apps.products.models import ProductVariant
from .models import StockItem, ProductionBatch, StockMovement


class InventoryService:
    """
    Authoritative, concurrency-safe inventory and batch tracking service.
    All stock state mutations are executed in atomic transactions with row locks
    to guarantee positive inventory balances and eliminate race conditions.
    """

    @classmethod
    def get_or_create_stock_item(cls, variant: ProductVariant) -> StockItem:
        stock, _ = StockItem.objects.get_or_create(
            variant=variant,
            defaults={
                'quantity_on_hand': 0,
                'reserved_quantity': 0,
                'low_stock_threshold': 20,
            }
        )
        return stock

    @classmethod
    @transaction.atomic
    def record_stock_in(
        cls,
        variant: ProductVariant,
        quantity: int,
        movement_type: str = 'production_in',
        batch: ProductionBatch = None,
        reference: str = '',
        reason: str = '',
        user=None
    ) -> StockItem:
        if quantity <= 0:
            raise ValidationError("Stock quantity must be greater than zero.")

        stock = StockItem.objects.select_for_update().get_or_create(
            variant=variant,
            defaults={'quantity_on_hand': 0, 'reserved_quantity': 0, 'low_stock_threshold': 20}
        )[0]

        stock.quantity_on_hand += quantity
        stock.save(update_fields=['quantity_on_hand', 'updated_at'])

        StockMovement.objects.create(
            variant=variant,
            batch=batch,
            movement_type=movement_type,
            quantity=quantity,
            reference_number=reference,
            reason=reason or f"Stock added via {movement_type}.",
            balance_after=stock.available_to_sell,
            user=user
        )

        return stock

    @classmethod
    @transaction.atomic
    def record_stock_out(
        cls,
        variant: ProductVariant,
        quantity: int,
        movement_type: str = 'damage',
        batch: ProductionBatch = None,
        reference: str = '',
        reason: str = '',
        user=None
    ) -> StockItem:
        if quantity <= 0:
            raise ValidationError("Stock quantity must be greater than zero.")

        stock = StockItem.objects.select_for_update().get_or_create(
            variant=variant,
            defaults={'quantity_on_hand': 0, 'reserved_quantity': 0, 'low_stock_threshold': 20}
        )[0]

        if stock.available_to_sell < quantity:
            raise ValidationError(
                f"Cannot remove {quantity} units of {variant.sku}. Available to sell: {stock.available_to_sell}."
            )

        stock.quantity_on_hand -= quantity
        stock.save(update_fields=['quantity_on_hand', 'updated_at'])

        if batch:
            batch = ProductionBatch.objects.select_for_update().get(id=batch.id)
            deduct_from_batch = min(batch.remaining_quantity, quantity)
            batch.remaining_quantity -= deduct_from_batch
            if batch.remaining_quantity == 0:
                batch.status = 'exhausted'
            batch.save(update_fields=['remaining_quantity', 'status', 'updated_at'])

        StockMovement.objects.create(
            variant=variant,
            batch=batch,
            movement_type=movement_type,
            quantity=quantity,
            reference_number=reference,
            reason=reason or f"Stock removed via {movement_type}.",
            balance_after=stock.available_to_sell,
            user=user
        )

        return stock

    @classmethod
    @transaction.atomic
    def record_stock_adjustment(
        cls,
        variant: ProductVariant,
        new_quantity_on_hand: int,
        reason: str = '',
        user=None
    ) -> StockItem:
        if new_quantity_on_hand < 0:
            raise ValidationError("Inventory count cannot be negative.")

        stock = StockItem.objects.select_for_update().get_or_create(
            variant=variant,
            defaults={'quantity_on_hand': 0, 'reserved_quantity': 0, 'low_stock_threshold': 20}
        )[0]

        if new_quantity_on_hand < stock.reserved_quantity:
            raise ValidationError(
                f"Adjusted quantity ({new_quantity_on_hand}) cannot be less than currently reserved order stock ({stock.reserved_quantity})."
            )

        diff = new_quantity_on_hand - stock.quantity_on_hand
        stock.quantity_on_hand = new_quantity_on_hand
        stock.save(update_fields=['quantity_on_hand', 'updated_at'])

        StockMovement.objects.create(
            variant=variant,
            movement_type='adjustment',
            quantity=abs(diff),
            reference_number='AUDIT-ADJUST',
            reason=reason or f"Stock count adjusted from {stock.quantity_on_hand - diff} to {new_quantity_on_hand}.",
            balance_after=stock.available_to_sell,
            user=user
        )

        return stock

    @classmethod
    @transaction.atomic
    def complete_production_batch(cls, batch: ProductionBatch, user=None) -> ProductionBatch:
        """
        Completes manufacturing batch, marks quality approved, and adds manufactured quantity
        to inventory. Idempotent: checks is_stock_added to prevent double crediting.
        """
        batch = ProductionBatch.objects.select_for_update().get(id=batch.id)

        if batch.is_stock_added:
            return batch

        batch.status = 'completed'
        batch.remaining_quantity = batch.manufactured_quantity
        batch.is_stock_added = True
        batch.save(update_fields=['status', 'remaining_quantity', 'is_stock_added', 'updated_at'])

        cls.record_stock_in(
            variant=batch.variant,
            quantity=batch.manufactured_quantity,
            movement_type='production_in',
            batch=batch,
            reference=batch.batch_number,
            reason=f"Production batch {batch.batch_number} completed in Vandiperiyar kitchen.",
            user=user or batch.created_by
        )

        return batch

    @classmethod
    @transaction.atomic
    def reserve_order_stock(cls, order, user=None):
        """
        Reserves required stock for an order across all its line items.
        Prevents overselling. Fails atomically if any item has insufficient stock.
        """
        if getattr(order, 'is_stock_reserved', False) or getattr(order, 'is_stock_deducted', False):
            return

        order_items = list(order.items.select_related('variant').all())

        # Step 1: Pre-check all variant quantities with row locks
        for item in order_items:
            if not item.variant:
                continue

            stock = StockItem.objects.select_for_update().get_or_create(
                variant=item.variant,
                defaults={'quantity_on_hand': 0, 'reserved_quantity': 0, 'low_stock_threshold': 20}
            )[0]

            if stock.available_to_sell < item.quantity:
                raise ValidationError(
                    f"Insufficient stock for {item.product_name} ({item.display_weight}). "
                    f"Required: {item.quantity}, Available: {stock.available_to_sell}."
                )

        # Step 2: Apply reservations and log movements
        for item in order_items:
            if not item.variant:
                continue

            stock = StockItem.objects.select_for_update().get(variant=item.variant)
            stock.reserved_quantity += item.quantity
            stock.save(update_fields=['reserved_quantity', 'updated_at'])

            StockMovement.objects.create(
                variant=item.variant,
                movement_type='order_reservation',
                quantity=item.quantity,
                reference_number=order.order_number,
                reason=f"Stock reserved for Order {order.order_number}.",
                balance_after=stock.available_to_sell,
                user=user
            )

        order.is_stock_reserved = True
        order.save(update_fields=['is_stock_reserved', 'updated_at'])

    @classmethod
    @transaction.atomic
    def release_order_stock(cls, order, user=None):
        """
        Releases reserved stock if an order is cancelled before dispatch.
        """
        if not getattr(order, 'is_stock_reserved', False) or getattr(order, 'is_stock_deducted', False):
            return

        order_items = list(order.items.select_related('variant').all())

        for item in order_items:
            if not item.variant:
                continue

            stock = StockItem.objects.select_for_update().filter(variant=item.variant).first()
            if not stock:
                continue

            stock.reserved_quantity = max(0, stock.reserved_quantity - item.quantity)
            stock.save(update_fields=['reserved_quantity', 'updated_at'])

            StockMovement.objects.create(
                variant=item.variant,
                movement_type='reservation_release',
                quantity=item.quantity,
                reference_number=order.order_number,
                reason=f"Stock reservation released due to cancellation of Order {order.order_number}.",
                balance_after=stock.available_to_sell,
                user=user
            )

        order.is_stock_reserved = False
        order.save(update_fields=['is_stock_reserved', 'updated_at'])

    @classmethod
    @transaction.atomic
    def dispatch_order_stock(cls, order, user=None):
        """
        Deducts physical stock upon order dispatch.
        Uses First-Expired-First-Out (FEFO) allocation across active non-expired production batches.
        """
        if getattr(order, 'is_stock_deducted', False):
            return

        order_items = list(order.items.select_related('variant').all())
        today = timezone.localdate()

        for item in order_items:
            if not item.variant:
                continue

            stock = StockItem.objects.select_for_update().get_or_create(
                variant=item.variant,
                defaults={'quantity_on_hand': 0, 'reserved_quantity': 0, 'low_stock_threshold': 20}
            )[0]

            # If order was reserved, decrement reserved_quantity
            if getattr(order, 'is_stock_reserved', False):
                stock.reserved_quantity = max(0, stock.reserved_quantity - item.quantity)

            # Deduct physical quantity on hand
            stock.quantity_on_hand = max(0, stock.quantity_on_hand - item.quantity)
            stock.save(update_fields=['quantity_on_hand', 'reserved_quantity', 'updated_at'])

            # FEFO Batch Allocation: allocate from earliest expiring non-expired batches first
            batches = ProductionBatch.objects.select_for_update().filter(
                variant=item.variant,
                status='completed',
                remaining_quantity__gt=0,
                expiry_date__gte=today
            ).order_by('expiry_date')

            remaining_to_allocate = item.quantity
            for batch in batches:
                if remaining_to_allocate <= 0:
                    break
                deduct = min(batch.remaining_quantity, remaining_to_allocate)
                batch.remaining_quantity -= deduct
                if batch.remaining_quantity == 0:
                    batch.status = 'exhausted'
                batch.save(update_fields=['remaining_quantity', 'status', 'updated_at'])
                remaining_to_allocate -= deduct

            StockMovement.objects.create(
                variant=item.variant,
                movement_type='order_dispatch',
                quantity=item.quantity,
                reference_number=order.order_number,
                reason=f"Stock dispatched for Order {order.order_number} using FEFO batch allocation.",
                balance_after=stock.available_to_sell,
                user=user
            )

        order.is_stock_deducted = True
        order.is_stock_reserved = False
        order.save(update_fields=['is_stock_deducted', 'is_stock_reserved', 'updated_at'])

