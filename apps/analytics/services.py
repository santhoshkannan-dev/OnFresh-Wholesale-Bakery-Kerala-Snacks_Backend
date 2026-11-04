"""
OnFresh Business Analytics & Aggregation Engine.
Provides high-performance, accurate timezone-aware sales, B2B/B2C, and inventory metrics.
"""

from decimal import Decimal
from datetime import datetime, time, timedelta
from django.utils import timezone
from django.db.models import (
    Sum,
    Count,
    Avg,
    F,
    Q,
    Value,
    DecimalField,
    IntegerField,
)
from django.db.models.functions import TruncDate, TruncWeek, TruncMonth, Coalesce

from ..orders.models import Order, OrderItem, Payment
from ..customers.models import CustomerProfile
from ..products.models import Product, ProductVariant, Category
from ..inventory.models import StockItem, ProductionBatch, StockMovement


def parse_date_range(period=None, start_date_str=None, end_date_str=None):
    """
    Computes timezone-aware (start_datetime, end_datetime) boundaries.
    Defaults to 'this_month' if not specified.
    """
    now = timezone.now()
    today_start = timezone.make_aware(datetime.combine(now.date(), time.min))
    today_end = timezone.make_aware(datetime.combine(now.date(), time.max))

    if period == 'today':
        return today_start, today_end
    elif period == 'yesterday':
        y = now.date() - timedelta(days=1)
        return timezone.make_aware(datetime.combine(y, time.min)), timezone.make_aware(datetime.combine(y, time.max))
    elif period == '7days':
        return today_start - timedelta(days=6), today_end
    elif period == '30days':
        return today_start - timedelta(days=29), today_end
    elif period == 'this_month':
        first_day = now.date().replace(day=1)
        return timezone.make_aware(datetime.combine(first_day, time.min)), today_end
    elif period == 'last_month':
        first_of_this = now.date().replace(day=1)
        last_of_prev = first_of_this - timedelta(days=1)
        first_of_prev = last_of_prev.replace(day=1)
        return timezone.make_aware(datetime.combine(first_of_prev, time.min)), timezone.make_aware(datetime.combine(last_of_prev, time.max))
    elif period == 'this_year':
        first_day = now.date().replace(month=1, day=1)
        return timezone.make_aware(datetime.combine(first_day, time.min)), today_end
    elif period == 'all':
        return timezone.make_aware(datetime(2020, 1, 1, 0, 0, 0)), today_end

    # Custom range
    if start_date_str:
        try:
            s_date = datetime.strptime(start_date_str.strip(), '%Y-%m-%d').date()
            start_dt = timezone.make_aware(datetime.combine(s_date, time.min))
        except (ValueError, TypeError):
            start_dt = today_start - timedelta(days=29)
    else:
        start_dt = today_start - timedelta(days=29)

    if end_date_str:
        try:
            e_date = datetime.strptime(end_date_str.strip(), '%Y-%m-%d').date()
            end_dt = timezone.make_aware(datetime.combine(e_date, time.max))
        except (ValueError, TypeError):
            end_dt = today_end
    else:
        end_dt = today_end

    return start_dt, end_dt


class AnalyticsService:
    """
    Central service for executive metrics, sales trends, B2B vs B2C comparisons, and reporting.
    """

    @classmethod
    def get_dashboard_summary(cls, start_dt, end_dt):
        """
        Calculates all high-level KPI cards for the executive dashboard.
        Guarantees:
        - Cancelled orders are excluded from completed net sales.
        - Unpaid orders are not counted as collected revenue.
        - Converted to precise Decimal values.
        """
        all_orders = Order.objects.filter(created_at__range=(start_dt, end_dt))
        valid_orders = all_orders.exclude(order_status='cancelled')

        # 1. Revenue calculations
        net_sales = valid_orders.aggregate(
            total=Coalesce(Sum('total_amount'), Value(Decimal('0.00'), output_field=DecimalField()))
        )['total']

        gross_value = valid_orders.aggregate(
            total=Coalesce(Sum('subtotal'), Value(Decimal('0.00'), output_field=DecimalField()))
        )['total']

        # Collected payments in this period
        collected_payments = Payment.objects.filter(
            order__created_at__range=(start_dt, end_dt),
            status='successful'
        ).aggregate(
            total=Coalesce(Sum('amount'), Value(Decimal('0.00'), output_field=DecimalField()))
        )['total']

        # Fallback if payments not recorded via gateway, check paid orders
        if collected_payments == Decimal('0.00'):
            collected_payments = valid_orders.filter(payment_status='paid').aggregate(
                total=Coalesce(Sum('total_amount'), Value(Decimal('0.00'), output_field=DecimalField()))
            )['total']

        outstanding_payments = valid_orders.filter(
            payment_status__in=['pending', 'partially_paid']
        ).aggregate(
            total=Coalesce(Sum('total_amount'), Value(Decimal('0.00'), output_field=DecimalField()))
        )['total']

        cancelled_amount = all_orders.filter(order_status='cancelled').aggregate(
            total=Coalesce(Sum('total_amount'), Value(Decimal('0.00'), output_field=DecimalField()))
        )['total']

        # 2. Order counts
        total_orders_count = all_orders.count()
        pending_count = all_orders.filter(order_status='pending').count()
        confirmed_count = all_orders.filter(order_status='confirmed').count()
        processing_count = all_orders.filter(order_status__in=['processing', 'ready_for_dispatch']).count()
        dispatched_count = all_orders.filter(order_status='dispatched').count()
        delivered_count = all_orders.filter(order_status='delivered').count()
        cancelled_count = all_orders.filter(order_status='cancelled').count()

        # 3. Customer metrics
        total_individual_customers = CustomerProfile.objects.filter(customer_type='individual').count()
        total_wholesale_customers = CustomerProfile.objects.filter(customer_type='business', wholesale_status='approved').count()
        pending_wholesale_applications = CustomerProfile.objects.filter(customer_type='business', wholesale_status='pending').count()

        # 4. Inventory & Catalog metrics
        total_active_products = Product.objects.filter(is_active=True).count()
        low_stock_variants = StockItem.objects.filter(
            quantity_on_hand__lte=F('reserved_quantity') + F('low_stock_threshold')
        ).count()
        out_of_stock_variants = StockItem.objects.filter(
            quantity_on_hand__lte=F('reserved_quantity')
        ).count()
        active_production_batches = ProductionBatch.objects.filter(
            status__in=['in_production', 'quarantined']
        ).count()

        # 5. Recent orders snapshot (latest 6)
        recent_orders_qs = all_orders.select_related('customer').order_by('-created_at')[:6]
        recent_orders = [
            {
                'id': o.id,
                'order_number': o.order_number,
                'customer_email': o.customer.email,
                'customer_name': o.customer.get_full_name() or o.customer.username,
                'customer_type': o.customer_type,
                'order_status': o.order_status,
                'order_status_display': o.get_order_status_display(),
                'payment_status': o.payment_status,
                'payment_status_display': o.get_payment_status_display(),
                'total_amount': float(o.total_amount),
                'created_at': o.created_at.isoformat(),
            }
            for o in recent_orders_qs
        ]

        # 6. Average order value (AOV)
        valid_orders_count = valid_orders.count()
        aov = (net_sales / valid_orders_count) if valid_orders_count > 0 else Decimal('0.00')

        return {
            'total_revenue': float(net_sales),
            'gross_order_value': float(gross_value),
            'collected_payments': float(collected_payments),
            'outstanding_payments': float(outstanding_payments),
            'cancelled_amount': float(cancelled_amount),
            'aov': float(aov),
            'total_orders': total_orders_count,
            'valid_orders_count': valid_orders_count,
            'pending_orders': pending_count,
            'confirmed_orders': confirmed_count,
            'processing_orders': processing_count,
            'dispatched_orders': dispatched_count,
            'delivered_orders': delivered_count,
            'cancelled_orders': cancelled_count,
            'total_individual_customers': total_individual_customers,
            'total_wholesale_customers': total_wholesale_customers,
            'pending_wholesale_applications': pending_wholesale_applications,
            'total_active_products': total_active_products,
            'low_stock_variants': low_stock_variants,
            'out_of_stock_variants': out_of_stock_variants,
            'active_production_batches': active_production_batches,
            'recent_orders': recent_orders,
        }

    @classmethod
    def get_sales_analytics(cls, start_dt, end_dt, interval='daily'):
        """
        Time-series sales metrics grouped by day or month.
        Returns data points formatted for frontend charting (bar/sparkline).
        """
        valid_orders = Order.objects.filter(
            created_at__range=(start_dt, end_dt)
        ).exclude(order_status='cancelled')

        if interval == 'monthly':
            trunc_fn = TruncMonth('created_at')
        elif interval == 'weekly':
            trunc_fn = TruncWeek('created_at')
        else:
            trunc_fn = TruncDate('created_at')

        time_series = valid_orders.annotate(
            period=trunc_fn
        ).values('period').annotate(
            total_revenue=Coalesce(Sum('total_amount'), Value(Decimal('0.00'), output_field=DecimalField())),
            retail_revenue=Coalesce(
                Sum('total_amount', filter=Q(customer_type='individual')),
                Value(Decimal('0.00'), output_field=DecimalField())
            ),
            wholesale_revenue=Coalesce(
                Sum('total_amount', filter=Q(customer_type='business')),
                Value(Decimal('0.00'), output_field=DecimalField())
            ),
            order_count=Count('id'),
            retail_orders=Count('id', filter=Q(customer_type='individual')),
            wholesale_orders=Count('id', filter=Q(customer_type='business')),
        ).order_by('period')

        formatted_series = []
        for entry in time_series:
            period_val = entry['period']
            if isinstance(period_val, datetime):
                label = period_val.strftime('%b %Y' if interval == 'monthly' else '%d %b')
                iso_date = period_val.date().isoformat()
            else:
                label = period_val.strftime('%d %b') if period_val else ''
                iso_date = period_val.isoformat() if period_val else ''

            count = entry['order_count']
            rev = entry['total_revenue']
            aov = (rev / count) if count > 0 else Decimal('0.00')

            formatted_series.append({
                'date': iso_date,
                'label': label,
                'total_revenue': float(rev),
                'retail_revenue': float(entry['retail_revenue']),
                'wholesale_revenue': float(entry['wholesale_revenue']),
                'order_count': count,
                'retail_orders': entry['retail_orders'],
                'wholesale_orders': entry['wholesale_orders'],
                'aov': float(aov),
            })

        # Payment methods breakdown
        payment_methods = valid_orders.values('payment_method').annotate(
            total=Coalesce(Sum('total_amount'), Value(Decimal('0.00'), output_field=DecimalField())),
            count=Count('id')
        ).order_by('-total')

        formatted_methods = [
            {
                'method': m['payment_method'],
                'display': dict(Order.PAYMENT_METHOD_CHOICES).get(m['payment_method'], m['payment_method']),
                'total': float(m['total']),
                'count': m['count'],
            }
            for m in payment_methods
        ]

        return {
            'time_series': formatted_series,
            'payment_breakdown': formatted_methods,
        }

    @classmethod
    def get_b2b_b2c_comparison(cls, start_dt, end_dt):
        """
        Comprehensive comparison between Retail (B2C) and Wholesale (B2B) customer segments.
        Matches customer_type snapshots from order records.
        """
        valid_orders = Order.objects.filter(
            created_at__range=(start_dt, end_dt)
        ).exclude(order_status='cancelled')

        def analyze_segment(ctype):
            seg_orders = valid_orders.filter(customer_type=ctype)
            total_rev = seg_orders.aggregate(
                total=Coalesce(Sum('total_amount'), Value(Decimal('0.00'), output_field=DecimalField()))
            )['total']
            order_count = seg_orders.count()
            aov = (total_rev / order_count) if order_count > 0 else Decimal('0.00')
            
            # Distinct customers who ordered
            distinct_customers = seg_orders.values('customer').distinct().count()
            
            # Repeat customer rate
            repeat_customers = seg_orders.values('customer').annotate(
                o_count=Count('id')
            ).filter(o_count__gt=1).count()
            repeat_rate = (repeat_customers / distinct_customers * 100) if distinct_customers > 0 else 0.0

            # Top products in this segment
            top_items = OrderItem.objects.filter(
                order__in=seg_orders
            ).values('product_name').annotate(
                units_sold=Sum('quantity'),
                revenue=Sum('line_total')
            ).order_by('-revenue')[:5]

            top_products = [
                {
                    'product_name': item['product_name'],
                    'units_sold': item['units_sold'],
                    'revenue': float(item['revenue']),
                }
                for item in top_items
            ]

            # Package size performance
            sizes = OrderItem.objects.filter(
                order__in=seg_orders
            ).values('package_weight', 'package_unit').annotate(
                units_sold=Sum('quantity'),
                revenue=Sum('line_total')
            ).order_by('-revenue')[:5]

            package_performance = [
                {
                    'size': f"{s['package_weight']:.0f} {s['package_unit']}" if s['package_weight'] == int(s['package_weight']) else f"{s['package_weight']:.2f} {s['package_unit']}",
                    'units_sold': s['units_sold'],
                    'revenue': float(s['revenue']),
                }
                for s in sizes
            ]

            return {
                'total_revenue': float(total_rev),
                'order_count': order_count,
                'aov': float(aov),
                'distinct_customers': distinct_customers,
                'repeat_customers': repeat_customers,
                'repeat_rate': round(repeat_rate, 1),
                'top_products': top_products,
                'package_performance': package_performance,
            }

        retail_metrics = analyze_segment('individual')
        wholesale_metrics = analyze_segment('business')

        # Overall revenue split percentage
        total_rev = retail_metrics['total_revenue'] + wholesale_metrics['total_revenue']
        retail_percent = (retail_metrics['total_revenue'] / total_rev * 100) if total_rev > 0 else 50.0
        wholesale_percent = 100.0 - retail_percent

        return {
            'retail': retail_metrics,
            'wholesale': wholesale_metrics,
            'revenue_split': {
                'retail_percent': round(retail_percent, 1),
                'wholesale_percent': round(wholesale_percent, 1),
            }
        }

    @classmethod
    def get_product_analytics(cls, start_dt, end_dt, category_id=None):
        """
        Deep-dive product performance: best/least selling, category share, and stock metrics.
        """
        items_qs = OrderItem.objects.filter(
            order__created_at__range=(start_dt, end_dt)
        ).exclude(order__order_status='cancelled')

        if category_id:
            items_qs = items_qs.filter(variant__product__category_id=category_id)

        # Best selling by revenue
        best_by_rev = items_qs.values(
            'product_name', 'sku', 'package_weight', 'package_unit'
        ).annotate(
            total_units=Sum('quantity'),
            total_revenue=Sum('line_total'),
            order_count=Count('order', distinct=True)
        ).order_by('-total_revenue')[:8]

        # Least selling by revenue
        least_by_rev = items_qs.values(
            'product_name', 'sku', 'package_weight', 'package_unit'
        ).annotate(
            total_units=Sum('quantity'),
            total_revenue=Sum('line_total'),
            order_count=Count('order', distinct=True)
        ).order_by('total_revenue')[:8]

        # Category performance
        category_sales = items_qs.filter(
            variant__product__category__isnull=False
        ).values(
            'variant__product__category__id',
            'variant__product__category__name'
        ).annotate(
            units_sold=Sum('quantity'),
            total_revenue=Sum('line_total')
        ).order_by('-total_revenue')

        formatted_categories = [
            {
                'category_id': c['variant__product__category__id'],
                'category_name': c['variant__product__category__name'],
                'units_sold': c['units_sold'],
                'total_revenue': float(c['total_revenue']),
            }
            for c in category_sales
        ]

        def format_product_list(items):
            result = []
            for item in items:
                wt = item['package_weight']
                unit = item['package_unit']
                wt_str = f"{wt:.0f} {unit}" if wt == int(wt) else f"{wt:.2f} {unit}"
                result.append({
                    'product_name': item['product_name'],
                    'sku': item['sku'],
                    'package_size': wt_str,
                    'total_units': item['total_units'],
                    'total_revenue': float(item['total_revenue']),
                    'order_count': item['order_count'],
                })
            return result

        return {
            'best_selling': format_product_list(best_by_rev),
            'least_selling': format_product_list(least_by_rev),
            'category_sales': formatted_categories,
        }
