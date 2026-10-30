from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("progreso", views.ProgresoViewSet, basename="progreso")
router.register("dificultades", views.DificultadViewSet, basename="dificultad")
urlpatterns = [
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    path("dashboard/exportar/", views.ExportarReporteView.as_view(), name="exportar-reporte"),
    path("docente/estudiantes/", views.DocenteEstudiantesView.as_view(), name="docente-estudiantes"),
] + router.urls
