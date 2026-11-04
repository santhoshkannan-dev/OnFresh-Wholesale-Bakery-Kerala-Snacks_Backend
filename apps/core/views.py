from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.db import connection
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """
    Health check API endpoint.
    Checks:
    - Backend application status
    - Database connection health
    - Server timestamp
    """
    db_status = "unhealthy"
    db_error = None
    
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
            row = cursor.fetchone()
            if row and row[0] == 1:
                db_status = "connected"
    except Exception as e:
        logger.warning(f"Database health check failed: {e}")
        db_status = "disconnected"
        db_error = str(e)

    payload = {
        "status": "healthy" if db_status == "connected" else "degraded",
        "service": "OnFresh Backend API",
        "version": "1.0.0",
        "timestamp": timezone.now().isoformat(),
        "database": {
            "engine": connection.settings_dict.get('ENGINE', '').split('.')[-1],
            "name": connection.settings_dict.get('NAME'),
            "status": db_status,
        }
    }
    
    if db_error:
        payload["database"]["error_detail"] = db_error

    # Return 200 even if DB is disconnected so frontend receives detailed diagnostics
    return Response(payload, status=status.HTTP_200_OK)
