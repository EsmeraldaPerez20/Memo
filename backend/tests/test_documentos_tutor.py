import io
from datetime import timedelta

from django.core.management import call_command
from django.utils import timezone

from apps.academico.models import UsuarioMateria
from apps.administracion.models import ConsumoIA, Notificacion
from apps.documentos.models import Documento, Fragmento, Material
from apps.tutor.models import Conversacion, Mensaje, ReporteIA
from servicios import almacenamiento

from .base import TEXTO_FOTOSINTESIS, BaseAPI


class DocumentosTests(BaseAPI):
    def setUp(self):
        self.m, self.t1, self.t2 = self.catalogo()
        self.ana, self.beto = self.usuario("ana@mail.com"), self.usuario("beto@mail.com")
        self.entrar(self.ana)

    def subir(self, nombre="apuntes.txt", contenido=TEXTO_FOTOSINTESIS, tipo="text/plain", **extra):
        return self.client.post("/api/documentos/", {"archivo": self.archivo(nombre, contenido, tipo), **extra}, format="multipart")

    def test_subir_y_analizar(self):
        r = self.subir(analizar="true", materia=self.m.id)
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual((r.data["estado_analisis"], r.data["tipo_archivo"]), ("completado", "txt"))
        self.assertNotIn("archivo_url", r.data)                                   # la ruta interna no se expone
        frag = Fragmento.objects.filter(documento_id=r.data["id"]).first()
        self.assertEqual(len(frag.embedding), 1536)
        el = self.client.get(f"/api/documentos/{r.data['id']}/elementos/").data
        self.assertTrue({"resumen", "concepto", "palabra_clave", "pregunta"} <= set(el))
        self.assertIn("fotosintesis", [e["contenido"] for e in el["palabra_clave"]])

    def test_cada_estudiante_solo_ve_sus_documentos(self):
        id_ = self.subir().data["id"]
        self.entrar(self.beto)
        self.assertEqual(self.client.get("/api/documentos/").data["count"], 0)
        for ruta in (f"/api/documentos/{id_}/", f"/api/documentos/{id_}/descargar/", f"/api/documentos/{id_}/elementos/"):
            self.assertEqual(self.client.get(ruta).status_code, 404, ruta)
        self.assertEqual(self.client.delete(f"/api/documentos/{id_}/").status_code, 404)

    def test_validaciones_de_archivo(self):
        self.assertEqual(self.subir("virus.exe", b"MZ").status_code, 400)
        self.assertEqual(self.subir("grande.txt", b"x" * (21 * 1024 * 1024)).status_code, 400)       # RF-14: maximo 20 MB
        self.assertEqual(self.subir("vacio.txt", b"").status_code, 400)
        self.assertEqual(self.client.post("/api/documentos/", {}, format="multipart").status_code, 400)

    def test_limite_configurable_por_el_administrador(self):
        from apps.administracion.models import ConfiguracionSistema
        ConfiguracionSistema.objects.filter(pk="max_archivo_mb").update(valor=1)
        self.assertEqual(self.subir("dos.txt", b"x" * (2 * 1024 * 1024)).status_code, 400)
        self.assertEqual(self.subir("uno.txt", b"hola mundo").status_code, 201)

    def test_lee_pdf_word_y_powerpoint(self):
        import docx
        import pptx
        from reportlab.pdfgen import canvas
        texto = "La mitocondria produce energia para la celula durante la respiracion celular."
        pdf, word, ppt = io.BytesIO(), io.BytesIO(), io.BytesIO()
        c = canvas.Canvas(pdf)
        c.drawString(72, 720, texto)
        c.save()
        d = docx.Document()
        d.add_paragraph(texto)
        d.save(word)
        prs = pptx.Presentation()
        s = prs.slides.add_slide(prs.slide_layouts[1])
        s.shapes.title.text, s.placeholders[1].text = "Mitocondria", texto
        prs.save(ppt)
        for nombre, datos in (("a.pdf", pdf), ("b.docx", word), ("c.pptx", ppt)):
            r = self.subir(nombre, datos.getvalue(), analizar="true")
            self.assertEqual((r.status_code, r.data["estado_analisis"]), (201, "completado"), (nombre, r.data))
            self.assertIn("mitocondria", Fragmento.objects.filter(documento_id=r.data["id"]).first().contenido.lower(), nombre)

    def test_imagen_sin_ocr_se_reporta_con_claridad(self):
        r = self.subir("foto.png", b"\x89PNG\r\n\x1a\n" + b"0" * 50, analizar="true")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["estado_analisis"], "error")
        self.assertIn("OCR", r.data["analisis_error"])

    def test_eliminar_borra_archivo_y_fragmentos(self):
        id_ = self.subir(analizar="true").data["id"]
        ruta = Documento.objects.get(pk=id_).archivo_url
        self.assertTrue(almacenamiento.leer(ruta))
        self.assertEqual(self.client.delete(f"/api/documentos/{id_}/").status_code, 204)
        self.assertEqual(self.client.get(f"/api/documentos/{id_}/").status_code, 404)
        self.assertEqual(Fragmento.objects.filter(documento_id=id_).count(), 0)         # lo hace el trigger de la base (RF-20)
        with self.assertRaises(almacenamiento.AlmacenamientoError):
            almacenamiento.leer(ruta)
        self.assertIsNotNone(Documento.objects.get(pk=id_).fecha_eliminacion)

    def test_descargar_y_enlace(self):
        id_ = self.subir().data["id"]
        r = self.client.get(f"/api/documentos/{id_}/descargar/")
        self.assertEqual((r.status_code, b"".join(r.streaming_content)), (200, TEXTO_FOTOSINTESIS.encode()))
        self.assertIn("/descargar/", self.client.get(f"/api/documentos/{id_}/enlace/").data["url"])

    def test_confirmar_materia_y_tema_sugeridos(self):
        id_ = self.subir(analizar="true", materia=self.m.id).data["id"]
        sug = self.client.get(f"/api/documentos/{id_}/temas/").data
        self.assertEqual([(s["nombre"], s["sugerido_por_ia"], s["confirmado"]) for s in sug], [("Fotosintesis", True, False)])
        r = self.client.post(f"/api/documentos/{id_}/temas/", {"materia": self.m.id, "temas": [self.t2.id]}, format="json")
        self.assertEqual([(s["nombre"], s["confirmado"]) for s in r.data], [("Respiracion celular", True)])


class MaterialesTests(BaseAPI):
    def setUp(self):
        self.m, self.t1, _ = self.catalogo()
        self.docente, self.alumno, self.otro = self.usuario("luis@mail.com", "docente"), self.usuario("ana@mail.com"), self.usuario("beto@mail.com")
        UsuarioMateria.objects.create(usuario=self.docente, materia=self.m, relacion="imparte")
        UsuarioMateria.objects.create(usuario=self.alumno, materia=self.m, relacion="cursa")

    def subir(self, **extra):
        return self.client.post("/api/materiales/", {"archivo": self.archivo("guia.txt", TEXTO_FOTOSINTESIS, "text/plain"), "materia": self.m.id,
                                                      "titulo": "Guia de fotosintesis", **extra}, format="multipart")

    def test_flujo_de_aprobacion(self):
        self.entrar(self.docente)
        r = self.subir()
        self.assertEqual((r.status_code, r.data["estado"]), (201, "pendiente"), r.content)
        id_ = r.data["id"]
        self.assertEqual(Fragmento.objects.filter(material_id=id_).count(), 0)          # aun no se usa en el tutor
        self.entrar(self.alumno)
        self.assertEqual(self.client.get("/api/materiales/").data["count"], 0)          # RF-47: pendiente = invisible
        self.assertEqual(self.client.get(f"/api/materiales/{id_}/").status_code, 404)
        self.assertEqual(self.client.post(f"/api/materiales/{id_}/aprobar/").status_code, 403)
        self.entrar(self.docente)
        a = self.client.post(f"/api/materiales/{id_}/aprobar/", {"comentarios": "Bien"}, format="json")
        self.assertEqual((a.status_code, a.data["estado"]), (200, "aprobado"), a.content)
        self.assertEqual(Material.objects.get(pk=id_).revisado_por_id, self.docente.id)
        self.assertGreaterEqual(Fragmento.objects.filter(material_id=id_).count(), 1)
        self.entrar(self.alumno)
        self.assertEqual(self.client.get("/api/materiales/").data["count"], 1)
        self.assertEqual(self.client.get(f"/api/materiales/{id_}/descargar/").status_code, 200)
        self.assertTrue(Notificacion.objects.filter(usuario=self.alumno, tipo="material", canal="app").exists())

    def test_el_tutor_usa_materiales_aprobados_solo_para_quien_cursa_la_materia(self):
        self.entrar(self.docente)
        id_ = self.subir().data["id"]
        self.client.post(f"/api/materiales/{id_}/aprobar/")
        for quien, esperado in ((self.alumno, "material"), (self.otro, None)):
            self.entrar(quien)
            c = self.client.post("/api/conversaciones/", {}, format="json").data["id"]
            r = self.client.post(f"/api/conversaciones/{c}/preguntar/", {"contenido": "¿Que es la fotosintesis?"}, format="json")
            self.assertEqual(r.status_code, 201, r.content)
            if esperado:
                self.assertEqual((r.data["fuentes"][0]["tipo"], r.data["advertencia_ia"]), ("material", False))
            else:
                self.assertEqual((r.data["fuentes"], r.data["advertencia_ia"]), ([], True))

    def test_docente_sin_la_materia_no_puede_subir(self):
        self.entrar(self.usuario("x@mail.com", "docente"))
        self.assertEqual(self.subir().status_code, 403)
        self.entrar(self.alumno)
        self.assertEqual(self.subir().status_code, 403)

    def test_rechazar_exige_motivo_y_avisa(self):
        self.entrar(self.docente)
        id_ = self.subir().data["id"]
        self.assertEqual(self.client.post(f"/api/materiales/{id_}/rechazar/", {}, format="json").status_code, 400)
        r = self.client.post(f"/api/materiales/{id_}/rechazar/", {"comentarios": "Falta bibliografia"}, format="json")
        self.assertEqual((r.status_code, r.data["estado"]), (200, "rechazado"))
        self.assertTrue(Notificacion.objects.filter(usuario=self.docente, tipo="material", titulo__startswith="Material rechazado").exists())


class TutorTests(BaseAPI):
    def setUp(self):
        self.m, self.t1, _ = self.catalogo()
        self.ana, self.beto, self.docente = self.usuario("ana@mail.com"), self.usuario("beto@mail.com"), self.usuario("luis@mail.com", "docente")
        self.entrar(self.ana)
        self.client.post("/api/documentos/", {"archivo": self.archivo("apuntes.txt", TEXTO_FOTOSINTESIS, "text/plain"), "analizar": "true"}, format="multipart")
        self.conv = self.client.post("/api/conversaciones/", {"guardada": True}, format="json").data["id"]

    def preguntar(self, texto, modo="normal", conv=None):
        return self.client.post(f"/api/conversaciones/{conv or self.conv}/preguntar/", {"contenido": texto, "modo_explicacion": modo}, format="json")

    def test_responde_con_fuentes_y_registra_consumo(self):
        r = self.preguntar("¿Que es la fotosintesis?")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual((r.data["emisor"], r.data["advertencia_ia"]), ("ia", False))
        self.assertEqual(r.data["fuentes"][0]["nombre"], "apuntes.txt")                  # RF-53
        self.assertIn("fotosintesis", r.data["fuentes"][0]["extracto"].lower())
        self.assertTrue(ConsumoIA.objects.filter(mensaje_id=r.data["id"], funcion="tutor").exists())   # RNF-25
        self.assertEqual(self.client.get(f"/api/conversaciones/{self.conv}/").data["titulo"], "¿Que es la fotosintesis?")
        self.assertEqual(len(self.client.get(f"/api/conversaciones/{self.conv}/mensajes/").data), 2)

    def test_modos_de_explicacion(self):
        self.assertTrue(self.preguntar("¿Que es la fotosintesis?", "sencilla").data["contenido"].startswith("En palabras simples"))
        self.assertEqual(self.preguntar("¿Que es la fotosintesis?", "inexistente").status_code, 400)

    def test_advierte_cuando_no_hay_informacion(self):
        r = self.preguntar("¿Cual es la capital de Francia?")
        self.assertEqual((r.data["advertencia_ia"], r.data["fuentes"]), (True, []))        # RF-12, RNF-23
        self.assertIn("no puedo asegurarte", r.data["contenido"])

    def test_no_usa_apuntes_de_otros_estudiantes(self):
        self.entrar(self.beto)
        c = self.client.post("/api/conversaciones/", {}, format="json").data["id"]
        r = self.preguntar("¿Que es la fotosintesis?", conv=c)
        self.assertEqual((r.data["advertencia_ia"], r.data["fuentes"]), (True, []))         # RF-19
        self.assertEqual(self.client.get(f"/api/conversaciones/{self.conv}/").status_code, 404)
        self.assertEqual(self.preguntar("hola", conv=self.conv).status_code, 404)

    def test_conversacion_sobre_un_documento_propio(self):
        doc = self.client.get("/api/documentos/").data["results"][0]["id"]
        c = self.client.post("/api/conversaciones/", {"documento": doc}, format="json")
        self.assertEqual(c.status_code, 201, c.content)
        self.assertEqual(self.preguntar("¿Que es la fotosintesis?", conv=c.data["id"]).data["fuentes"][0]["tipo"], "documento")
        self.entrar(self.beto)
        self.assertEqual(self.client.post("/api/conversaciones/", {"documento": doc}, format="json").status_code, 400)

    def test_reporte_de_respuesta_sobrevive_al_borrado_de_la_conversacion(self):
        msg = self.preguntar("¿Que es la fotosintesis?").data
        r = self.client.post(f"/api/mensajes/{msg['id']}/reportar/", {"motivo": "incorrecta", "comentario": "Esta mal"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(self.client.delete(f"/api/conversaciones/{self.conv}/").status_code, 204)      # RF-11
        self.assertEqual(Mensaje.objects.filter(conversacion_id=self.conv).count(), 0)
        reporte = ReporteIA.objects.get()
        self.assertIsNone(reporte.mensaje_id)
        self.assertEqual(reporte.contenido_reportado, msg["contenido"])                                 # la copia se conserva
        self.assertTrue(ConsumoIA.objects.filter(mensaje__isnull=True, funcion="tutor").exists())
        # un mensaje que no es suyo o que no es de la IA no se puede reportar
        self.assertEqual(self.client.post(f"/api/mensajes/{msg['id']}/reportar/", {"motivo": "otro"}, format="json").status_code, 404)

    def test_revision_de_reportes_por_docentes(self):
        msg = self.preguntar("¿Que es la fotosintesis?").data
        self.client.post(f"/api/mensajes/{msg['id']}/reportar/", {"motivo": "incompleta"}, format="json")
        id_ = ReporteIA.objects.get().id
        self.assertEqual(self.client.get("/api/reportes-ia/").status_code, 403)
        self.entrar(self.docente)
        r = self.client.patch(f"/api/reportes-ia/{id_}/", {"estado": "revisado", "motivo": "otro"}, format="json")
        self.assertEqual((r.status_code, r.data["estado"], r.data["motivo"]), (200, "revisado", "incompleta"))   # el motivo no se puede cambiar
        self.assertEqual(ReporteIA.objects.get().revisado_por_id, self.docente.id)

    def test_conversaciones_no_guardadas_se_purgan(self):
        sin = self.client.post("/api/conversaciones/", {"guardada": False}, format="json").data["id"]
        Conversacion.objects.filter(pk__in=[sin, self.conv]).update(fecha_ultima_actividad=timezone.now() - timedelta(hours=30))
        call_command("purgar_conversaciones", "--horas", "24")
        self.assertEqual(set(Conversacion.objects.values_list("id", flat=True)), {self.conv})          # solo queda la que autorizo guardar
