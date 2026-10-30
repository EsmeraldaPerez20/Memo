from rest_framework.response import Response
from rest_framework.views import exception_handler


def manejador(exc, context):
    """Convierte los errores del servicio de IA en 503 con un mensaje claro para el frontend."""
    from servicios.ia import IAError
    if isinstance(exc, IAError):
        return Response({"detail": str(exc)}, status=503)
    return exception_handler(exc, context)
