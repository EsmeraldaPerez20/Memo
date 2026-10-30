from django.contrib import admin
from django.urls import include, path
from drf_spectacular.utils import extend_schema
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@extend_schema(responses={200: {"type": "object"}})
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([])
def salud(request):
    """Para que Render compruebe que el servicio esta vivo."""
    return Response({"estado": "ok", "servicio": "memo-backend"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/salud/", salud),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("api/", include("apps.usuarios.urls")),
    path("api/", include("apps.academico.urls")),
    path("api/", include("apps.documentos.urls")),
    path("api/", include("apps.tutor.urls")),
    path("api/", include("apps.evaluaciones.urls")),
    path("api/", include("apps.diagnostico.urls")),
    path("api/", include("apps.planificacion.urls")),
    path("api/", include("apps.administracion.urls")),
]
