from django.contrib import admin
from django.urls import path
from rest_framework.decorators import api_view
from rest_framework.response import Response


@api_view(["GET"])
def health_check(request):
    """Endpoint simple para confirmar que la API está viva."""
    return Response({"status": "ok", "proyecto": "FourMind (Memo)"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health_check, name="health-check"),

    # Conforme se desarrollen los módulos, se agregan aquí, por ejemplo:
    # path("api/usuarios/", include("apps.usuarios.urls")),
    # path("api/tutor/", include("apps.tutor.urls")),
]
