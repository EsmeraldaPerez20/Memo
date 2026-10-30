import tempfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.usuarios.models import Rol, Usuario

_TMP = tempfile.mkdtemp(prefix="memo_pruebas_")


@override_settings(ALMACENAMIENTO_LOCAL=Path(_TMP))
class BaseAPI(APITestCase):
    PWD = "Clave-Segura-123"

    def usuario(self, correo, rol="estudiante", nombre="Persona", password=None, **extra):
        return Usuario.objects.create_user(correo, nombre, password or self.PWD, rol=Rol.objects.get(nombre=rol), **extra)

    def entrar(self, usuario_o_correo, password=None):
        correo = getattr(usuario_o_correo, "correo", usuario_o_correo)
        r = self.client.post("/api/auth/login/", {"correo": correo, "password": password or self.PWD}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + r.data["access"])
        return r.data

    def salir(self):
        self.client.credentials()

    def catalogo(self):
        from apps.academico.models import Materia, Tema, Unidad
        m = Materia.objects.create(nombre="Biologia")
        u = Unidad.objects.create(materia=m, nombre="Celula", orden=1)
        return m, Tema.objects.create(unidad=u, nombre="Fotosintesis", orden=1), Tema.objects.create(unidad=u, nombre="Respiracion celular", orden=2)

    def archivo(self, nombre, contenido, tipo="application/octet-stream"):
        return SimpleUploadedFile(nombre, contenido if isinstance(contenido, bytes) else contenido.encode(), content_type=tipo)


TEXTO_FOTOSINTESIS = (
    "La fotosintesis es el proceso mediante el cual las plantas convierten la luz solar en energia quimica. "
    "Durante la fotosintesis, los cloroplastos absorben luz y producen glucosa y oxigeno a partir de agua y dioxido de carbono. "
    "La fotosintesis ocurre en dos fases: la fase luminosa y el ciclo de Calvin. "
    "Sin fotosintesis no habria oxigeno suficiente para los organismos aerobios.")
