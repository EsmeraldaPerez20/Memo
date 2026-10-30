from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("conversaciones", views.ConversacionViewSet, basename="conversacion")
router.register("reportes-ia", views.ReporteIAViewSet, basename="reporte-ia")
urlpatterns = [path("mensajes/<int:pk>/reportar/", views.ReportarMensajeView.as_view(), name="reportar-mensaje")] + router.urls
