from django.db import IntegrityError
from rest_framework.response import Response
from rest_framework.views import exception_handler


def api_exception_handler(error, context):
    # Constraint conflicts are client-visible, but database details stay private.
    if isinstance(error, IntegrityError):
        return Response({"detail": "The change conflicts with existing records."}, status=409)
    # Preserve DRF's normal responses for validation, permissions and other errors.
    return exception_handler(error, context)
