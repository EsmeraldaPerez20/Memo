from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("materias", views.MateriaViewSet, basename="materia")
router.register("unidades", views.UnidadViewSet, basename="unidad")
router.register("temas", views.TemaViewSet, basename="tema")

urlpatterns = [
    path("mis-materias/", views.MisMateriasView.as_view(), name="mis-materias"),
    path("mis-materias/<int:materia_id>/", views.MiMateriaDetalleView.as_view(), name="mi-materia"),
] + router.urls
