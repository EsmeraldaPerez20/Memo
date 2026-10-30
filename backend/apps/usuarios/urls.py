from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenBlacklistView

from . import views

router = DefaultRouter()
router.register("usuarios", views.UsuarioAdminViewSet, basename="usuario")
router.register("roles", views.RolViewSet, basename="rol")
router.register("permisos", views.PermisoViewSet, basename="permiso")

urlpatterns = [
    path("auth/registro/", views.RegistroView.as_view(), name="registro"),
    path("auth/login/", views.LoginView.as_view(), name="login"),
    path("auth/refresh/", views.RefreshView.as_view(), name="refresh"),
    path("auth/logout/", TokenBlacklistView.as_view(), name="logout"),
    path("auth/google/", views.GoogleLoginView.as_view(), name="login-google"),
    path("auth/recuperar/", views.RecuperarView.as_view(), name="recuperar"),
    path("auth/restablecer/", views.RestablecerView.as_view(), name="restablecer"),
    path("auth/yo/", views.YoView.as_view(), name="yo"),
    path("auth/perfil/", views.PerfilView.as_view(), name="perfil"),
    path("auth/preferencias/", views.PreferenciasView.as_view(), name="preferencias"),
] + router.urls
