"""Uniform API error envelope.

Without this, DRF returns errors in three different shapes depending on where
they came from (serialiser validation, permission denied, or an unhandled
exception). Clients end up writing three parsers. This normalises all of them to
``{"error": {"code": ..., "message": ..., "details": {...}}}``.
"""

import logging

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.http import Http404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)

CODE_BY_STATUS = {
    400: "validation_error",
    401: "not_authenticated",
    403: "permission_denied",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    429: "throttled",
}


def _envelope(code: str, message: str, details=None, status_code=status.HTTP_400_BAD_REQUEST):
    body = {"error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return Response(body, status=status_code)


def error_response(
    message: str,
    *,
    code: str = "validation_error",
    details=None,
    status_code=status.HTTP_400_BAD_REQUEST,
):
    """Build an error in the same envelope the exception handler produces.

    A view that returns ``Response(status=400)`` directly bypasses the handler
    and would otherwise emit a different body shape from every error that does
    go through a serialiser, leaving clients to parse two formats.
    """
    return _envelope(code, message, details, status_code)


def api_exception_handler(exc, context):
    if isinstance(exc, DjangoValidationError):
        return _envelope(
            "validation_error", "The submitted data is invalid.", exc.message_dict
        )

    if isinstance(exc, DjangoPermissionDenied):
        return _envelope("permission_denied", str(exc) or "Permission denied.", status_code=status.HTTP_403_FORBIDDEN)

    if isinstance(exc, Http404):
        return _envelope("not_found", "Resource not found.", status_code=status.HTTP_404_NOT_FOUND)

    if isinstance(exc, IntegrityError):
        # Never leak the raw constraint text - it discloses table structure.
        logger.warning("IntegrityError on %s", context.get("request"), exc_info=exc)
        return _envelope(
            "conflict",
            "That change conflicts with data that already exists.",
            status_code=status.HTTP_409_CONFLICT,
        )

    response = exception_handler(exc, context)
    if response is None:
        logger.exception("Unhandled API error", exc_info=exc)
        return _envelope(
            "internal_error",
            "Something went wrong on our end.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    detail = response.data
    if isinstance(detail, dict) and "error" in detail:
        return response

    code = CODE_BY_STATUS.get(response.status_code, "error")
    if response.status_code in {400, 409} and isinstance(detail, dict):
        message = "Please correct the highlighted fields."
        return _envelope(code, message, detail, response.status_code)
    if isinstance(detail, dict) and "detail" in detail:
        return _envelope(code, str(detail["detail"]), status_code=response.status_code)

    return _envelope(code, "Request failed.", detail, response.status_code)
