# Render the exploration page and expose a database-backed readiness endpoint.
import logging

from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_safe

logger = logging.getLogger(__name__)


@require_safe
def explore(request):
    return render(request, "explore.html")


@require_safe
def health(request):
    """Readiness checks database connectivity and the required spatial extension."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT PostGIS_Version()")
            cursor.fetchone()
    except DatabaseError:
        logger.exception("Database readiness check failed")
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})
