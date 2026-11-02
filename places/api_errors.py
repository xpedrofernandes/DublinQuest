from django.db import IntegrityError
from rest_framework.response import Response
from rest_framework.views import exception_handler


def api_exception_handler(error, context):
    if isinstance(error, IntegrityError):
        return Response({"detail": "The change conflicts with existing records."}, status=409)
    return exception_handler(error, context)
