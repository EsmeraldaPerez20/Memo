from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("recomendaciones", views.RecomendacionViewSet, basename="recomendacion")
router.register("planes", views.PlanEstudioViewSet, basename="plan")
router.register("plan-items", views.PlanItemViewSet, basename="plan-item")
router.register("metas", views.MetaViewSet, basename="meta")
router.register("tareas", views.TareaViewSet, basename="tarea")
urlpatterns = router.urls
