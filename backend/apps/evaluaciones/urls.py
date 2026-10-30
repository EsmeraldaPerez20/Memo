from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("banco-preguntas", views.BancoPreguntaViewSet, basename="banco-pregunta")
router.register("actividades", views.ActividadViewSet, basename="actividad")
router.register("intentos", views.IntentoViewSet, basename="intento")
urlpatterns = router.urls
