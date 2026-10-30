from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("notificaciones", views.NotificacionViewSet, basename="notificacion")
router.register("auditoria", views.BitacoraViewSet, basename="auditoria")
router.register("incidencias", views.IncidenciaViewSet, basename="incidencia")
router.register("consumo-ia", views.ConsumoIAViewSet, basename="consumo-ia")
router.register("configuracion", views.ConfiguracionViewSet, basename="configuracion")
urlpatterns = router.urls
