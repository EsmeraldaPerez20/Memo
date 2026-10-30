from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("documentos", views.DocumentoViewSet, basename="documento")
router.register("materiales", views.MaterialViewSet, basename="material")
urlpatterns = router.urls
