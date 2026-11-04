"""
OnFresh Analytics API Views.
Protected by IsAdminUser / Staff permissions.
"""

from django.http import HttpResponse
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser

from .services import AnalyticsService, parse_date_range
from .reports import ReportExportService


class DashboardSummaryView(APIView):
    """
    Returns executive summary metrics and KPIs for the OnFresh admin dashboard.
    Query parameters:
    - period: today, yesterday, 7days, 30days, this_month, last_month, this_year, all
    - start_date, end_date: YYYY-MM-DD (custom range)
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        period = request.query_params.get('period', 'this_month')
        start_str = request.query_params.get('start_date')
        end_str = request.query_params.get('end_date')

        start_dt, end_dt = parse_date_range(period, start_str, end_str)
        data = AnalyticsService.get_dashboard_summary(start_dt, end_dt)
        data['period'] = period
        data['start_date'] = start_dt.date().isoformat()
        data['end_date'] = end_dt.date().isoformat()

        return Response({'status': 'success', 'data': data})


class SalesAnalyticsView(APIView):
    """
    Returns time-series revenue and volume data for bar/sparkline charts.
    Query parameters:
    - period, start_date, end_date
    - interval: daily, weekly, monthly
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        period = request.query_params.get('period', '30days')
        interval = request.query_params.get('interval', 'daily')
        start_str = request.query_params.get('start_date')
        end_str = request.query_params.get('end_date')

        start_dt, end_dt = parse_date_range(period, start_str, end_str)
        data = AnalyticsService.get_sales_analytics(start_dt, end_dt, interval=interval)
        data['interval'] = interval
        data['start_date'] = start_dt.date().isoformat()
        data['end_date'] = end_dt.date().isoformat()

        return Response({'status': 'success', 'data': data})


class B2BvsB2CComparisonView(APIView):
    """
    Detailed comparison between Retail (individual) and Wholesale (business) customer orders.
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        period = request.query_params.get('period', 'this_month')
        start_str = request.query_params.get('start_date')
        end_str = request.query_params.get('end_date')

        start_dt, end_dt = parse_date_range(period, start_str, end_str)
        data = AnalyticsService.get_b2b_b2c_comparison(start_dt, end_dt)
        data['start_date'] = start_dt.date().isoformat()
        data['end_date'] = end_dt.date().isoformat()

        return Response({'status': 'success', 'data': data})


class ProductAnalyticsView(APIView):
    """
    Best-selling and least-selling products, category breakdown, and stock performance.
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        period = request.query_params.get('period', 'this_month')
        start_str = request.query_params.get('start_date')
        end_str = request.query_params.get('end_date')
        category_id = request.query_params.get('category_id')

        start_dt, end_dt = parse_date_range(period, start_str, end_str)
        data = AnalyticsService.get_product_analytics(start_dt, end_dt, category_id=category_id)
        data['start_date'] = start_dt.date().isoformat()
        data['end_date'] = end_dt.date().isoformat()

        return Response({'status': 'success', 'data': data})


class ReportExportView(APIView):
    """
    Generates downloadable CSV or Excel reports for sales, orders, customers, inventory, products.
    Query parameters:
    - type: sales, orders, customers, inventory, products (default: sales)
    - format: csv, excel (default: csv)
    - period, start_date, end_date
    """
    permission_classes = [IsAdminUser]

    def perform_content_negotiation(self, request, force=False):
        """Bypass DRF renderer negotiation since this view directly streams raw CSV / Excel bytes."""
        return None, None

    def get(self, request):
        report_type = request.query_params.get('type', 'sales').lower()
        export_format = request.query_params.get('format', 'csv').lower()
        period = request.query_params.get('period', 'this_month')
        start_str = request.query_params.get('start_date')
        end_str = request.query_params.get('end_date')

        allowed_types = ['sales', 'orders', 'customers', 'inventory', 'products']
        if report_type not in allowed_types:
            return Response(
                {'status': 'error', 'detail': f"Invalid report type. Allowed: {', '.join(allowed_types)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        start_dt, end_dt = parse_date_range(period, start_str, end_str)
        content_bytes, mime_type, filename = ReportExportService.export(
            report_type, export_format, start_dt, end_dt
        )

        response = HttpResponse(content_bytes, content_type=mime_type)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
