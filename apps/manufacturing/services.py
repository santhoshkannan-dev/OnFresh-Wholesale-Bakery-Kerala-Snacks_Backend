from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from apps.inventory.models import ProductionBatch, StockItem
from apps.inventory.services import InventoryService
from .models import (
    RawMaterial,
    RawMaterialMovement,
    Supplier,
    PurchaseOrder,
    PurchaseOrderItem,
    SupplierPayment,
    Recipe,
    RecipeIngredient,
    RecipePackaging,
    ProductionOrder,
    ProductionMaterialConsumption,
    ProductionPackagingConsumption,
    QualityInspection,
)


class RawMaterialService:
    """
    Authoritative, concurrency-safe inventory service for raw materials and packaging.
    All state mutations use row-level locking to guarantee non-negative stock balances.
    """

    @classmethod
    @transaction.atomic
    def record_stock_in(
        cls,
        material: RawMaterial,
        quantity: Decimal,
        unit_cost: Decimal = Decimal('0.00'),
        reference_number: str = '',
        notes: str = '',
        user=None,
        movement_type: str = 'purchase_in'
    ) -> RawMaterial:
        if quantity <= Decimal('0.000'):
            raise ValidationError("Inward stock quantity must be greater than zero.")

        mat = RawMaterial.objects.select_for_update().get(id=material.id)
        mat.current_stock += quantity

        if unit_cost > Decimal('0.00'):
            mat.unit_cost = unit_cost

        mat.save(update_fields=['current_stock', 'unit_cost', 'updated_at'])

        total_cost = (quantity * (unit_cost or mat.unit_cost)).quantize(Decimal('0.01'))

        RawMaterialMovement.objects.create(
            material=mat,
            movement_type=movement_type,
            quantity=quantity,
            unit=mat.unit_of_measure,
            unit_cost=unit_cost or mat.unit_cost,
            total_cost=total_cost,
            balance_after=mat.current_stock,
            reference_number=reference_number,
            notes=notes or f"Stock added via {movement_type}.",
            created_by=user
        )
        return mat

    @classmethod
    @transaction.atomic
    def record_stock_out(
        cls,
        material: RawMaterial,
        quantity: Decimal,
        movement_type: str = 'production_consumption',
        reference_number: str = '',
        notes: str = '',
        user=None
    ) -> RawMaterial:
        if quantity <= Decimal('0.000'):
            raise ValidationError("Stock deduction quantity must be greater than zero.")

        mat = RawMaterial.objects.select_for_update().get(id=material.id)
        if mat.current_stock < quantity:
            raise ValidationError(
                f"Insufficient stock for {mat.name} ({mat.material_code}). Available: {mat.current_stock} {mat.unit_of_measure}, requested: {quantity} {mat.unit_of_measure}."
            )

        mat.current_stock -= quantity
        mat.save(update_fields=['current_stock', 'updated_at'])

        total_cost = (quantity * mat.unit_cost).quantize(Decimal('0.01'))

        RawMaterialMovement.objects.create(
            material=mat,
            movement_type=movement_type,
            quantity=quantity,
            unit=mat.unit_of_measure,
            unit_cost=mat.unit_cost,
            total_cost=total_cost,
            balance_after=mat.current_stock,
            reference_number=reference_number,
            notes=notes or f"Stock deducted via {movement_type}.",
            created_by=user
        )
        return mat

    @classmethod
    @transaction.atomic
    def record_adjustment(
        cls,
        material: RawMaterial,
        new_quantity: Decimal,
        notes: str = '',
        user=None
    ) -> RawMaterial:
        if new_quantity < Decimal('0.000'):
            raise ValidationError("Adjusted stock balance cannot be negative.")

        mat = RawMaterial.objects.select_for_update().get(id=material.id)
        diff = new_quantity - mat.current_stock
        mat.current_stock = new_quantity
        mat.save(update_fields=['current_stock', 'updated_at'])

        movement_type = 'adjustment'
        RawMaterialMovement.objects.create(
            material=mat,
            movement_type=movement_type,
            quantity=abs(diff),
            unit=mat.unit_of_measure,
            unit_cost=mat.unit_cost,
            total_cost=(abs(diff) * mat.unit_cost).quantize(Decimal('0.01')),
            balance_after=mat.current_stock,
            reference_number='AUDIT-ADJUST',
            notes=notes or f"Physical stock adjusted from {new_quantity - diff} to {new_quantity}.",
            created_by=user
        )
        return mat


class PurchaseService:
    """
    Purchase Order lifecycle and goods receipt processing.
    Ensures strict separation between purchase ordering and inventory stock-in.
    """

    @classmethod
    @transaction.atomic
    def receive_purchase_order(
        cls,
        purchase_order: PurchaseOrder,
        received_items: list = None,
        vendor_invoice_number: str = '',
        user=None
    ) -> PurchaseOrder:
        po = PurchaseOrder.objects.select_for_update().get(id=purchase_order.id)

        if po.is_stock_added:
            return po

        if po.status == 'cancelled':
            raise ValidationError("Cannot receive a cancelled purchase order.")

        # If specific received quantities were passed, update line items
        if received_items:
            item_map = {item['id']: Decimal(str(item.get('received_quantity', 0))) for item in received_items if 'id' in item}
            for line in po.items.all():
                if line.id in item_map:
                    line.received_quantity = item_map[line.id]
                else:
                    line.received_quantity = line.ordered_quantity
                line.save(update_fields=['received_quantity'])
        else:
            for line in po.items.all():
                line.received_quantity = line.ordered_quantity
                line.save(update_fields=['received_quantity'])

        # Credit stock for each received material
        for line in po.items.all():
            if line.received_quantity > Decimal('0.000'):
                RawMaterialService.record_stock_in(
                    material=line.material,
                    quantity=line.received_quantity,
                    unit_cost=line.unit_cost,
                    reference_number=po.po_number,
                    notes=f"Inward receipt from PO {po.po_number} ({po.supplier.name})",
                    user=user,
                    movement_type='purchase_in'
                )

        po.is_stock_added = True
        po.status = 'received'
        po.received_date = timezone.localdate()
        if vendor_invoice_number:
            po.vendor_invoice_number = vendor_invoice_number
        po.save(update_fields=['is_stock_added', 'status', 'received_date', 'vendor_invoice_number', 'updated_at'])
        return po

    @classmethod
    @transaction.atomic
    def record_supplier_payment(
        cls,
        purchase_order: PurchaseOrder,
        amount: Decimal,
        payment_method: str = 'bank_transfer',
        reference_number: str = '',
        notes: str = '',
        user=None
    ) -> SupplierPayment:
        po = PurchaseOrder.objects.select_for_update().get(id=purchase_order.id)

        if amount <= Decimal('0.00'):
            raise ValidationError("Payment amount must be greater than zero.")

        payment = SupplierPayment.objects.create(
            purchase_order=po,
            amount=amount,
            payment_method=payment_method,
            reference_number=reference_number,
            notes=notes,
            created_by=user
        )

        po.amount_paid += amount
        if po.amount_paid >= po.total_amount:
            po.payment_status = 'paid'
        elif po.amount_paid > Decimal('0.00'):
            po.payment_status = 'partially_paid'
        po.save(update_fields=['amount_paid', 'payment_status', 'updated_at'])

        return payment


class ProductionService:
    """
    Production planning, material reservation, actual consumption, and manufacturing execution.
    """

    @classmethod
    def check_ingredient_availability(cls, recipe: Recipe, target_units: int) -> dict:
        """
        Calculates raw materials and packaging required for target_units based on recipe yield.
        Returns detailed requirements and flags any inventory shortfall.
        """
        batch_yield = recipe.target_variant_units or int(recipe.batch_output_quantity) or 1
        scaling_factor = Decimal(str(target_units)) / Decimal(str(batch_yield))

        requirements = []
        shortfalls = []
        is_sufficient = True

        # Check raw ingredients
        for ing in recipe.ingredients.select_related('material').all():
            needed_qty = (ing.effective_quantity * scaling_factor).quantize(Decimal('0.001'))
            available_qty = ing.material.current_stock
            shortfall = max(Decimal('0.000'), needed_qty - available_qty)

            item_info = {
                'material_id': ing.material.id,
                'material_code': ing.material.material_code,
                'name': ing.material.name,
                'category': ing.material.category.name,
                'required_quantity': needed_qty,
                'available_quantity': available_qty,
                'unit': ing.unit,
                'has_shortfall': shortfall > Decimal('0.000'),
                'shortfall_quantity': shortfall,
            }
            requirements.append(item_info)
            if shortfall > Decimal('0.000'):
                is_sufficient = False
                shortfalls.append(item_info)

        # Check packaging materials
        for pkg in recipe.packaging_materials.select_related('packaging_material').all():
            needed_qty = (pkg.quantity * scaling_factor).quantize(Decimal('0.001'))
            available_qty = pkg.packaging_material.current_stock
            shortfall = max(Decimal('0.000'), needed_qty - available_qty)

            item_info = {
                'material_id': pkg.packaging_material.id,
                'material_code': pkg.packaging_material.material_code,
                'name': pkg.packaging_material.name,
                'category': pkg.packaging_material.category.name,
                'required_quantity': needed_qty,
                'available_quantity': available_qty,
                'unit': pkg.unit,
                'has_shortfall': shortfall > Decimal('0.000'),
                'shortfall_quantity': shortfall,
            }
            requirements.append(item_info)
            if shortfall > Decimal('0.000'):
                is_sufficient = False
                shortfalls.append(item_info)

        return {
            'is_sufficient': is_sufficient,
            'target_units': target_units,
            'scaling_factor': float(scaling_factor),
            'requirements': requirements,
            'shortfalls': shortfalls,
        }

    @classmethod
    @transaction.atomic
    def create_production_order(
        cls,
        recipe: Recipe,
        planned_quantity: int,
        start_date=None,
        notes: str = '',
        user=None
    ) -> ProductionOrder:
        if planned_quantity <= 0:
            raise ValidationError("Planned quantity must be at least 1 unit.")

        batch_yield = recipe.target_variant_units or int(recipe.batch_output_quantity) or 1
        scaling_factor = Decimal(str(planned_quantity)) / Decimal(str(batch_yield))

        variant = recipe.variant
        if not variant:
            variant = recipe.product.variants.first()
            if not variant:
                raise ValidationError(f"Product {recipe.product.name} has no package variants.")

        order = ProductionOrder.objects.create(
            recipe=recipe,
            product=recipe.product,
            variant=variant,
            planned_quantity=planned_quantity,
            start_date=start_date or timezone.localdate(),
            labor_cost=(recipe.estimated_labor_cost * scaling_factor).quantize(Decimal('0.01')),
            overhead_cost=(recipe.estimated_overhead_cost * scaling_factor).quantize(Decimal('0.01')),
            notes=notes,
            created_by=user,
            status='planned'
        )

        # Prepopulate planned consumptions
        for ing in recipe.ingredients.all():
            planned_qty = (ing.effective_quantity * scaling_factor).quantize(Decimal('0.001'))
            ProductionMaterialConsumption.objects.create(
                production_order=order,
                material=ing.material,
                planned_quantity=planned_qty,
                actual_quantity=planned_qty,
                unit=ing.unit,
                unit_cost=ing.material.unit_cost,
                total_cost=(planned_qty * ing.material.unit_cost).quantize(Decimal('0.01'))
            )

        for pkg in recipe.packaging_materials.all():
            planned_qty = (pkg.quantity * scaling_factor).quantize(Decimal('0.001'))
            ProductionPackagingConsumption.objects.create(
                production_order=order,
                material=pkg.packaging_material,
                planned_quantity=planned_qty,
                actual_quantity=planned_qty,
                unit=pkg.unit,
                unit_cost=pkg.packaging_material.unit_cost,
                total_cost=(planned_qty * pkg.packaging_material.unit_cost).quantize(Decimal('0.01'))
            )

        order.recalculate_costs()
        return order

    @classmethod
    @transaction.atomic
    def execute_and_send_to_qc(
        cls,
        production_order: ProductionOrder,
        produced_quantity: int,
        rejected_quantity: int = 0,
        actual_consumptions: list = None,
        actual_packagings: list = None,
        expiry_date=None,
        user=None
    ) -> tuple[ProductionOrder, ProductionBatch]:
        """
        Executes kitchen manufacturing run:
        1. Deducts actual raw materials and packaging from raw stock ledger.
        2. Calculates exact manufacturing cost.
        3. Creates a ProductionBatch in status 'quarantined' awaiting QC approval.
        4. Advances order status to 'quality_check'.
        """
        order = ProductionOrder.objects.select_for_update().get(id=production_order.id)

        if order.status in ['completed', 'cancelled']:
            raise ValidationError(f"Cannot execute order with status {order.status}.")

        if produced_quantity <= 0:
            raise ValidationError("Produced quantity must be greater than zero.")

        # Update and deduct actual material consumptions
        if actual_consumptions:
            mat_map = {item['id']: item for item in actual_consumptions if 'id' in item}
            for line in order.material_consumptions.select_related('material').all():
                if line.id in mat_map:
                    payload = mat_map[line.id]
                    line.actual_quantity = Decimal(str(payload.get('actual_quantity', line.planned_quantity)))
                    line.wastage_quantity = Decimal(str(payload.get('wastage_quantity', 0)))
                line.save()
                # Deduct from raw materials
                total_consumed = line.actual_quantity + line.wastage_quantity
                if total_consumed > Decimal('0.000'):
                    RawMaterialService.record_stock_out(
                        material=line.material,
                        quantity=total_consumed,
                        movement_type='production_consumption',
                        reference_number=order.order_number,
                        notes=f"Consumed in production order {order.order_number} ({order.variant.sku})",
                        user=user
                    )
        else:
            for line in order.material_consumptions.select_related('material').all():
                total_consumed = line.planned_quantity
                line.actual_quantity = total_consumed
                line.save()
                if total_consumed > Decimal('0.000'):
                    RawMaterialService.record_stock_out(
                        material=line.material,
                        quantity=total_consumed,
                        movement_type='production_consumption',
                        reference_number=order.order_number,
                        notes=f"Consumed in production order {order.order_number} ({order.variant.sku})",
                        user=user
                    )

        # Update and deduct actual packaging consumptions
        if actual_packagings:
            pkg_map = {item['id']: item for item in actual_packagings if 'id' in item}
            for line in order.packaging_consumptions.select_related('material').all():
                if line.id in pkg_map:
                    payload = pkg_map[line.id]
                    line.actual_quantity = Decimal(str(payload.get('actual_quantity', line.planned_quantity)))
                    line.wastage_quantity = Decimal(str(payload.get('wastage_quantity', 0)))
                line.save()
                total_consumed = line.actual_quantity + line.wastage_quantity
                if total_consumed > Decimal('0.000'):
                    RawMaterialService.record_stock_out(
                        material=line.material,
                        quantity=total_consumed,
                        movement_type='production_consumption',
                        reference_number=order.order_number,
                        notes=f"Packaging used in production order {order.order_number}",
                        user=user
                    )
        else:
            for line in order.packaging_consumptions.select_related('material').all():
                total_consumed = line.planned_quantity
                line.actual_quantity = total_consumed
                line.save()
                if total_consumed > Decimal('0.000'):
                    RawMaterialService.record_stock_out(
                        material=line.material,
                        quantity=total_consumed,
                        movement_type='production_consumption',
                        reference_number=order.order_number,
                        notes=f"Packaging used in production order {order.order_number}",
                        user=user
                    )

        order.produced_quantity = produced_quantity
        order.rejected_quantity = rejected_quantity
        order.status = 'quality_check'
        order.recalculate_costs()

        # Create or link Phase 6 ProductionBatch in 'quarantined' state
        if not expiry_date:
            expiry_date = timezone.localdate() + timezone.timedelta(days=90)  # Standard 90-day shelf life

        if not order.production_batch:
            batch = ProductionBatch.objects.create(
                product=order.product,
                variant=order.variant,
                production_date=order.start_date,
                expiry_date=expiry_date,
                manufactured_quantity=produced_quantity,
                remaining_quantity=0,  # Not released to sellable inventory yet!
                status='quarantined',
                manufacturing_notes=f"Produced via work order {order.order_number}. Cost per unit: ₹{order.cost_per_unit}",
                created_by=user,
                is_stock_added=False
            )
            order.production_batch = batch
        else:
            batch = order.production_batch
            batch.manufactured_quantity = produced_quantity
            batch.expiry_date = expiry_date
            batch.status = 'quarantined'
            batch.save(update_fields=['manufactured_quantity', 'expiry_date', 'status', 'updated_at'])

        order.save(update_fields=['produced_quantity', 'rejected_quantity', 'status', 'production_batch', 'updated_at'])
        return order, batch


class QualityService:
    """
    Quality Control inspection service. Acts as the mandatory gatekeeper.
    Batches that pass QC are released into Phase 6 finished-goods stock.
    Failed/quarantined batches are locked out of saleable inventory.
    """

    @classmethod
    @transaction.atomic
    def process_inspection(
        cls,
        production_order: ProductionOrder,
        sample_size: int,
        appearance_status: str,
        taste_crispness_status: str,
        moisture_status: str,
        packaging_seal_status: str,
        label_batch_verification: str,
        overall_result: str,
        defect_notes: str = '',
        corrective_actions: str = '',
        inspector=None
    ) -> QualityInspection:
        order = ProductionOrder.objects.select_for_update().get(id=production_order.id)
        batch = order.production_batch

        if not batch:
            raise ValidationError("Production order has no linked production batch to inspect.")

        # Determine release status
        if overall_result == 'passed':
            release_status = 'released'
        elif overall_result == 'failed':
            release_status = 'rejected'
        else:
            release_status = 'quarantined'

        inspection = QualityInspection.objects.create(
            production_order=order,
            production_batch=batch,
            inspector=inspector,
            sample_size=sample_size,
            appearance_status=appearance_status,
            taste_crispness_status=taste_crispness_status,
            moisture_status=moisture_status,
            packaging_seal_status=packaging_seal_status,
            label_batch_verification=label_batch_verification,
            overall_result=overall_result,
            release_status=release_status,
            defect_notes=defect_notes,
            corrective_actions=corrective_actions
        )

        if release_status == 'released':
            # Release batch to sellable inventory via InventoryService
            InventoryService.complete_production_batch(batch, user=inspector)
            order.status = 'completed'
            order.completion_date = timezone.localdate()
            order.save(update_fields=['status', 'completion_date', 'updated_at'])
        elif release_status == 'rejected':
            batch.status = 'recalled'
            batch.is_stock_added = False
            batch.save(update_fields=['status', 'is_stock_added', 'updated_at'])
        else:
            batch.status = 'quarantined'
            batch.is_stock_added = False
            batch.save(update_fields=['status', 'is_stock_added', 'updated_at'])

        return inspection

