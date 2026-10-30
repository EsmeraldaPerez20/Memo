from datetime import timedelta

from django.core import mail
from django.core.management import call_command
from django.db import connection
from django.utils import timezone

from apps.administracion.models import BitacoraAuditoria, ConsumoIA, Incidencia, Notificacion
from apps.diagnostico.models import Dificultad
from apps.usuarios.models import Usuario

from .base import TEXTO_FOTOSINTESIS, BaseAPI


class AdministracionTests(BaseAPI):
    def setUp(self):
        self.admin = Usuario.objects.create_superuser("admin@mail.com", "Admin", self.PWD)
        self.ana, self.beto = self.usuario("ana@mail.com"), self.usuario("beto@mail.com")

    def test_servicio_vivo_y_documentacion(self):
        self.assertEqual(self.client.get("/api/salud/").data["estado"], "ok")
        self.assertEqual(self.client.get("/api/schema/").status_code, 200)
        self.assertEqual(self.client.get("/api/docs/").status_code, 200)

    def test_incidencias(self):
        self.entrar(self.ana)
        r = self.client.post("/api/incidencias/", {"tipo": "falla_ia", "descripcion": "La IA no responde", "severidad": "alta"}, format="json")
        self.assertEqual((r.status_code, r.data["estado"]), (201, "abierta"), r.content)
        id_ = r.data["id"]
        self.assertEqual(self.client.patch(f"/api/incidencias/{id_}/", {"estado": "resuelta"}, format="json").status_code, 403)
        self.entrar(self.beto)
        self.assertEqual(self.client.get("/api/incidencias/").data["count"], 0)                       # solo ve las suyas
        self.entrar(self.admin)
        self.assertEqual(self.client.get("/api/incidencias/").data["count"], 1)
        r = self.client.patch(f"/api/incidencias/{id_}/", {"estado": "resuelta", "asignada_a": self.admin.id}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIsNotNone(Incidencia.objects.get().fecha_resolucion)

    def test_configuracion_del_sistema_cambia_el_comportamiento(self):
        self.entrar(self.admin)
        lista = self.client.get("/api/configuracion/").data
        self.assertTrue({"max_archivo_mb", "umbral_alerta_errores", "vigencia_token_recuperacion_min"} <= {c["clave"] for c in lista})
        r = self.client.patch("/api/configuracion/umbral_alerta_errores/", {"valor": 2}, format="json")
        self.assertEqual((r.status_code, r.data["valor"], r.data["actualizado_por"]), (200, 2, self.admin.id), r.content)
        self.assertEqual(self.client.get("/api/configuracion/ia.tiempo_objetivo_seg/").data["valor"], 15)       # claves con punto
        self.assertEqual(self.client.post("/api/configuracion/", {"clave": "nueva.clave", "valor": {"a": 1}}, format="json").status_code, 201)
        # con umbral = 2, la dificultad se detecta a la segunda actividad fallida
        from apps.academico.models import Materia, Tema, Unidad
        m = Materia.objects.create(nombre="Biologia")
        t = Tema.objects.create(unidad=Unidad.objects.create(materia=m, nombre="U"), nombre="Fotosintesis")
        self.entrar(self.ana)
        for _ in range(2):
            a = self.client.post("/api/actividades/generar/", {"materia": m.id, "temas": [t.id], "num_preguntas": 1, "tipos_pregunta": ["opcion_multiple"]}, format="json").data
            ini = self.client.post(f"/api/actividades/{a['id']}/iniciar/").data
            self.client.post(f"/api/intentos/{ini['id']}/responder/", {"pregunta": ini["preguntas"][0]["id"], "respuesta": "zzz"}, format="json")
            self.client.post(f"/api/intentos/{ini['id']}/finalizar/")
        self.assertEqual(Dificultad.objects.count(), 1)

    def test_bitacora_y_consumo_de_ia(self):
        self.entrar(self.ana)
        self.client.post("/api/documentos/", {"archivo": self.archivo("a.txt", TEXTO_FOTOSINTESIS, "text/plain"), "analizar": "true"}, format="multipart")
        c = self.client.post("/api/conversaciones/", {}, format="json").data["id"]
        self.client.post(f"/api/conversaciones/{c}/preguntar/", {"contenido": "¿Que es la fotosintesis?"}, format="json")
        self.assertEqual(self.client.get("/api/consumo-ia/").status_code, 403)
        self.entrar(self.admin)
        res = {(f["funcion"]) for f in self.client.get("/api/consumo-ia/resumen/").data}
        self.assertTrue({"tutor", "analisis_documento", "embeddings"} >= res >= {"tutor", "analisis_documento"} - {"embeddings"}, res)
        acciones = {b["accion"] for b in self.client.get("/api/auditoria/").data["results"]}
        self.assertTrue({"login", "subir_documento"} <= acciones, acciones)
        self.assertEqual(self.client.get("/api/auditoria/?accion=subir_documento").data["count"], 1)
        self.assertGreaterEqual(ConsumoIA.objects.count(), 2)

    def test_notificaciones_respetan_las_preferencias(self):
        from servicios import notificaciones
        self.entrar(self.ana)
        self.client.patch("/api/auth/preferencias/", {"notif_resultados": False, "canal_correo": True}, format="json")
        self.assertEqual(notificaciones.notificar(self.ana, "resultado", "Tu resultado"), [])                    # tipo desactivado
        creadas = notificaciones.notificar(self.ana, "recomendacion", "Repasa", "Mensaje")
        self.assertEqual(sorted(n.canal for n in creadas), ["app", "correo"])
        self.assertEqual((len(mail.outbox), mail.outbox[0].to), (1, ["ana@mail.com"]))
        self.assertEqual(self.client.get("/api/notificaciones/no-leidas/").data["no_leidas"], 1)
        n = self.client.get("/api/notificaciones/?canal=app").data["results"][0]
        self.assertEqual(self.client.patch(f"/api/notificaciones/{n['id']}/", {"leida": True, "titulo": "hack"}, format="json").data["titulo"], "Repasa")
        self.assertEqual(self.client.get("/api/notificaciones/no-leidas/").data["no_leidas"], 0)
        self.assertEqual(self.client.post("/api/notificaciones/marcar-todas/").data["marcadas"], 1)               # la del correo
        self.entrar(self.beto)
        self.assertEqual(self.client.get("/api/notificaciones/").data["count"], 0)
        self.assertEqual(self.client.patch(f"/api/notificaciones/{n['id']}/", {"leida": True}, format="json").status_code, 404)

    def test_recordatorios_de_tareas(self):
        self.entrar(self.ana)
        self.client.post("/api/tareas/", {"titulo": "Examen de Biologia", "tipo": "examen", "fecha_limite": (timezone.now() + timedelta(hours=3)).isoformat()}, format="json")
        self.client.post("/api/tareas/", {"titulo": "Lejana", "tipo": "tarea", "fecha_limite": (timezone.now() + timedelta(days=9)).isoformat()}, format="json")
        call_command("enviar_recordatorios")
        call_command("enviar_recordatorios")                                                                     # no duplica
        self.assertEqual(list(Notificacion.objects.filter(tipo="recordatorio").values_list("titulo", flat=True)), ["Recordatorio: Examen de Biologia"])

    def test_tareas(self):
        self.entrar(self.ana)
        t = self.client.post("/api/tareas/", {"titulo": "Leer capitulo 3"}, format="json")
        self.assertEqual((t.status_code, t.data["completada"], t.data["tipo"]), (201, False, "tarea"), t.content)
        r = self.client.patch(f"/api/tareas/{t.data['id']}/", {"completada": True}, format="json")
        self.assertTrue(r.data["completada"] and r.data["fecha_completada"])
        self.entrar(self.beto)
        self.assertEqual(self.client.get(f"/api/tareas/{t.data['id']}/").status_code, 404)

    def test_comando_que_protege_las_tablas_de_django(self):
        with connection.cursor() as c:
            c.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public' AND NOT rowsecurity")
            antes = c.fetchone()[0]
        self.assertGreaterEqual(antes, 7)                      # auth_*, django_*, token_blacklist_* creadas por migrate
        call_command("proteger_tablas")
        with connection.cursor() as c:
            c.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public' AND NOT rowsecurity")
            self.assertEqual(c.fetchone()[0], 0)
        self.entrar(self.ana)                                  # Django es dueno de las tablas: RLS no le estorba
        self.assertEqual(self.client.get("/api/auth/yo/").status_code, 200)
