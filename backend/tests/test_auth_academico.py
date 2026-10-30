import re
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.test import override_settings
from django.utils import timezone

from apps.academico.models import Materia, UsuarioMateria
from apps.administracion.models import BitacoraAuditoria
from apps.usuarios.models import TokenRecuperacion, Usuario

from .base import BaseAPI

REGISTRO = {"nombre": "Ana", "apellido": "Perez", "correo": "ana@mail.com", "password": "Clave-Segura-123",
            "carrera": "Biologia", "semestre": 3, "acepta_aviso": True}


class AutenticacionTests(BaseAPI):
    def test_registro_correcto(self):
        r = self.client.post("/api/auth/registro/", REGISTRO, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data["usuario"]["rol"], "estudiante")
        self.assertIn("tutor.usar", r.data["usuario"]["permisos"])
        self.assertNotIn("usuarios.gestionar", r.data["usuario"]["permisos"])
        self.assertEqual(r.data["usuario"]["perfil"]["carrera"], "Biologia")
        u = Usuario.objects.get(correo="ana@mail.com")
        self.assertNotEqual(u.password, REGISTRO["password"])          # RNF-04: nunca texto plano
        self.assertTrue(u.check_password(REGISTRO["password"]))
        self.assertIsNotNone(u.aviso_privacidad_aceptado_en)           # RNF-05
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + r.data["access"])
        self.assertEqual(self.client.get("/api/auth/yo/").status_code, 200)

    def test_registro_solo_exige_nombre_correo_y_password(self):
        r = self.client.post("/api/auth/registro/", {"nombre": "Beto", "correo": "beto@mail.com", "password": "Clave-Segura-123", "acepta_aviso": True}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertIsNone(Usuario.objects.get(correo="beto@mail.com").apellido)

    def test_registro_rechaza_datos_invalidos(self):
        self.client.post("/api/auth/registro/", REGISTRO, format="json")
        casos = [({"correo": "ANA@mail.com"}, "correo"),                     # duplicado sin importar mayusculas
                 ({"correo": "otra@mail.com", "acepta_aviso": False}, "acepta_aviso"),
                 ({"correo": "otra@mail.com", "password": "12345678"}, "password"),
                 ({"correo": "otra@mail.com", "telefono": "5512345678"}, "telefono")]
        for cambio, campo in casos:
            r = self.client.post("/api/auth/registro/", {**REGISTRO, **cambio}, format="json")
            self.assertEqual(r.status_code, 400, cambio)
            self.assertIn(campo, r.data, cambio)

    def test_login_y_bitacora(self):
        u = self.usuario("ana@mail.com")
        mal = self.client.post("/api/auth/login/", {"correo": "ana@mail.com", "password": "incorrecta-123"}, format="json")
        self.assertEqual(mal.status_code, 401)
        fallido = BitacoraAuditoria.objects.get(accion="login_fallido")
        self.assertEqual(fallido.detalle, {"correo": "ana@mail.com"})        # nunca se guarda la contrasena
        datos = self.entrar("ANA@mail.com")                                    # el correo no distingue mayusculas
        self.assertEqual(datos["usuario"]["correo"], "ana@mail.com")
        self.assertTrue(BitacoraAuditoria.objects.filter(accion="login", usuario=u).exists())
        u.refresh_from_db()
        self.assertIsNotNone(u.last_login)

    def test_usuario_desactivado_no_entra(self):
        u = self.usuario("ana@mail.com")
        u.is_active = False
        u.save()
        r = self.client.post("/api/auth/login/", {"correo": "ana@mail.com", "password": self.PWD}, format="json")
        self.assertEqual(r.status_code, 401)

    def test_sin_token_no_hay_acceso(self):
        self.assertEqual(self.client.get("/api/auth/yo/").status_code, 401)
        self.assertEqual(self.client.get("/api/documentos/").status_code, 401)

    def test_logout_invalida_el_refresh(self):
        self.usuario("ana@mail.com")
        datos = self.entrar("ana@mail.com")
        self.assertEqual(self.client.post("/api/auth/logout/", {"refresh": datos["refresh"]}, format="json").status_code, 200)
        self.salir()
        self.assertEqual(self.client.post("/api/auth/refresh/", {"refresh": datos["refresh"]}, format="json").status_code, 401)

    def test_recuperar_y_restablecer_contrasena(self):
        self.usuario("ana@mail.com")
        self.assertEqual(self.client.post("/api/auth/recuperar/", {"correo": "ANA@mail.com"}, format="json").status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        token = re.search(r"token=([\w-]+)", mail.outbox[0].body).group(1)
        # un correo que no existe recibe la misma respuesta y no envia nada (no revela cuentas)
        self.assertEqual(self.client.post("/api/auth/recuperar/", {"correo": "nadie@mail.com"}, format="json").status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(self.client.post("/api/auth/restablecer/", {"token": token, "password": "12345678"}, format="json").status_code, 400)
        self.assertEqual(self.client.post("/api/auth/restablecer/", {"token": token, "password": "Nueva-Clave-456"}, format="json").status_code, 200)
        self.entrar("ana@mail.com", "Nueva-Clave-456")
        self.salir()
        self.assertEqual(self.client.post("/api/auth/restablecer/", {"token": token, "password": "Otra-Clave-789"}, format="json").status_code, 400)  # un solo uso
        self.assertFalse(TokenRecuperacion.objects.filter(token_hash=token).exists())                                                              # solo se guarda el hash

    def test_token_de_recuperacion_expira(self):
        self.usuario("ana@mail.com")
        self.client.post("/api/auth/recuperar/", {"correo": "ana@mail.com"}, format="json")
        token = re.search(r"token=([\w-]+)", mail.outbox[0].body).group(1)
        TokenRecuperacion.objects.update(expira_en=timezone.now() - timedelta(minutes=1))
        self.assertEqual(self.client.post("/api/auth/restablecer/", {"token": token, "password": "Nueva-Clave-456"}, format="json").status_code, 400)

    def test_login_con_google(self):
        info = {"sub": "g-1", "email": "beto@gmail.com", "email_verified": True, "given_name": "Beto", "family_name": "Lopez"}
        self.assertEqual(self.client.post("/api/auth/google/", {"id_token": "x"}, format="json").status_code, 503)    # sin configurar
        with override_settings(GOOGLE_CLIENT_ID="cliente"), mock.patch("google.oauth2.id_token.verify_oauth2_token", return_value=info):
            r = self.client.post("/api/auth/google/", {"id_token": "x"}, format="json")
            self.assertEqual((r.status_code, r.data.get("codigo")), (400, "aviso_requerido"))
            r = self.client.post("/api/auth/google/", {"id_token": "x", "acepta_aviso": True}, format="json")
            self.assertEqual(r.status_code, 200, r.content)
            u = Usuario.objects.get(correo="beto@gmail.com")
            self.assertEqual((u.google_id, u.password), ("g-1", None))                      # sin contrasena
            self.assertEqual(self.client.post("/api/auth/google/", {"id_token": "x"}, format="json").status_code, 200)
            self.assertEqual(Usuario.objects.filter(correo="beto@gmail.com").count(), 1)
        mal = self.client.post("/api/auth/login/", {"correo": "beto@gmail.com", "password": "cualquiera-123"}, format="json")
        self.assertEqual(mal.status_code, 401)                                              # no entra con contrasena
        with override_settings(GOOGLE_CLIENT_ID="cliente"), mock.patch("google.oauth2.id_token.verify_oauth2_token", side_effect=ValueError("mala")):
            self.assertEqual(self.client.post("/api/auth/google/", {"id_token": "x"}, format="json").status_code, 400)

    def test_google_vincula_cuenta_existente(self):
        self.usuario("ana@mail.com")
        info = {"sub": "g-9", "email": "ana@mail.com", "email_verified": True}
        with override_settings(GOOGLE_CLIENT_ID="cliente"), mock.patch("google.oauth2.id_token.verify_oauth2_token", return_value=info):
            self.assertEqual(self.client.post("/api/auth/google/", {"id_token": "x"}, format="json").status_code, 200)
        u = Usuario.objects.get(correo="ana@mail.com")
        self.assertEqual(u.google_id, "g-9")
        self.assertTrue(u.check_password(self.PWD))                                         # su contrasena sigue funcionando

    def test_perfil_y_preferencias(self):
        self.usuario("ana@mail.com")
        self.entrar("ana@mail.com")
        self.assertEqual(self.client.patch("/api/auth/yo/", {"telefono": "5512"}, format="json").status_code, 400)
        r = self.client.patch("/api/auth/yo/", {"telefono": "+525512345678", "nombre": "Ana Maria"}, format="json")
        self.assertEqual((r.status_code, r.data["telefono"]), (200, "+525512345678"))
        self.assertEqual(self.client.patch("/api/auth/perfil/", {"carrera": "Quimica", "semestre": 5}, format="json").data["carrera"], "Quimica")
        p = self.client.patch("/api/auth/preferencias/", {"modo_oscuro": True, "canal_whatsapp": True, "tamano_letra": 20}, format="json")
        self.assertEqual((p.status_code, p.data["modo_oscuro"], p.data["canal_whatsapp"]), (200, True, True))


class AdministracionUsuariosTests(BaseAPI):
    def setUp(self):
        self.admin = Usuario.objects.create_superuser("admin@mail.com", "Admin", self.PWD)
        self.alumno = self.usuario("ana@mail.com")

    def test_estudiante_no_administra_usuarios(self):
        self.entrar(self.alumno)
        for url in ("/api/usuarios/", "/api/roles/", "/api/permisos/", "/api/auditoria/", "/api/configuracion/"):
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_admin_gestiona_usuarios_y_se_audita(self):
        self.entrar(self.admin)
        self.assertEqual(self.client.get("/api/usuarios/").status_code, 200)
        docente_id = self.client.get("/api/roles/").data[1]["id"]
        r = self.client.patch(f"/api/usuarios/{self.alumno.id}/", {"rol": docente_id}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(BitacoraAuditoria.objects.filter(accion="cambio_rol", entidad_id=self.alumno.id).exists())
        nuevo = self.client.post("/api/usuarios/", {"nombre": "Luis", "correo": "luis@mail.com", "password": "Clave-Segura-123", "rol": docente_id}, format="json")
        self.assertEqual(nuevo.status_code, 201, nuevo.content)
        self.assertTrue(Usuario.objects.get(correo="luis@mail.com").check_password("Clave-Segura-123"))

    def test_admin_asigna_permisos_a_un_rol(self):
        self.entrar(self.admin)
        rol = next(x for x in self.client.get("/api/roles/").data if x["nombre"] == "estudiante")
        r = self.client.put(f"/api/roles/{rol['id']}/permisos/", {"permisos": ["tutor.usar", "dashboard.ver"]}, format="json")
        self.assertEqual((r.status_code, r.data["permisos"]), (200, ["dashboard.ver", "tutor.usar"]))
        self.assertEqual(self.client.put(f"/api/roles/{rol['id']}/permisos/", {"permisos": ["no.existe"]}, format="json").status_code, 400)
        self.entrar(self.alumno)                                    # el cambio aplica de inmediato
        self.assertEqual(self.client.get("/api/documentos/").status_code, 403)


class AcademicoTests(BaseAPI):
    def setUp(self):
        self.alumno, self.docente = self.usuario("ana@mail.com"), self.usuario("luis@mail.com", "docente")

    def test_solo_quien_gestiona_modifica_el_catalogo(self):
        self.entrar(self.alumno)
        self.assertEqual(self.client.post("/api/materias/", {"nombre": "Fisica"}, format="json").status_code, 403)
        self.entrar(self.docente)
        r = self.client.post("/api/materias/", {"nombre": "Fisica"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Materia.objects.get(pk=r.data["id"]).creada_por_id, self.docente.id)
        self.entrar(self.alumno)
        self.assertEqual(self.client.get("/api/materias/").status_code, 200)

    def test_arbol_con_subtemas(self):
        m, t1, _ = self.catalogo()
        self.entrar(self.docente)
        self.client.post("/api/temas/", {"unidad": t1.unidad_id, "tema_padre": t1.id, "nombre": "Fase luminosa"}, format="json")
        r = self.client.get(f"/api/materias/{m.id}/arbol/")
        self.assertEqual(r.status_code, 200)
        tema = r.data["unidades"][0]["temas"][0]
        self.assertEqual((tema["nombre"], tema["subtemas"][0]["nombre"]), ("Fotosintesis", "Fase luminosa"))

    def test_inscribirse_a_materias(self):
        m, _, _ = self.catalogo()
        self.entrar(self.alumno)
        self.assertEqual(self.client.post("/api/mis-materias/", {"materia": m.id}, format="json").status_code, 201)
        self.assertEqual(self.client.post("/api/mis-materias/", {"materia": m.id}, format="json").status_code, 200)   # sin duplicar
        self.assertEqual(self.client.get("/api/mis-materias/").data[0]["relacion"], "cursa")
        self.assertEqual(self.client.delete(f"/api/mis-materias/{m.id}/").status_code, 204)
        self.assertEqual(self.client.get("/api/mis-materias/").data, [])
        self.entrar(self.docente)
        self.client.post("/api/mis-materias/", {"materia": m.id}, format="json")
        self.assertEqual(UsuarioMateria.objects.get(usuario=self.docente).relacion, "imparte")
