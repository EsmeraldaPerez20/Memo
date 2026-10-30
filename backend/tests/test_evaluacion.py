import io
import json
from collections import Counter
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.academico.models import UsuarioMateria
from apps.administracion.models import Notificacion
from apps.diagnostico.models import Dificultad, DificultadEvidencia, Progreso
from apps.evaluaciones.models import BancoPregunta, Intento
from apps.planificacion.models import Meta
from servicios import evaluacion as ev

from .base import BaseAPI

TODOS_LOS_TIPOS = ["opcion_multiple", "verdadero_falso", "completar_espacios", "abierta", "relacion_columnas", "problema_matematico", "practico"]


class FlujoEvaluacion(BaseAPI):
    def setUp(self):
        self.m, self.t1, self.t2 = self.catalogo()
        self.ana = self.usuario("ana@mail.com")
        self.entrar(self.ana)

    # ---- ayudantes
    def generar(self, **extra):
        datos = {"materia": self.m.id, "temas": [self.t1.id, self.t2.id], "tipo": "quiz", "dificultad": "media", "num_preguntas": 4, **extra}
        return self.client.post("/api/actividades/generar/", datos, format="json")

    def correcta(self, bp):
        return json.loads(bp.respuesta_correcta) if bp.tipo in ("completar_espacios", "relacion_columnas") else bp.respuesta_correcta

    def incorrecta(self, bp):
        return {"verdadero_falso": "falso" if bp.respuesta_correcta == "verdadero" else "verdadero", "completar_espacios": ["x"],
                "relacion_columnas": {"1": "zzz"}, "problema_matematico": "-1"}.get(bp.tipo, "zzz respuesta equivocada")

    def intento(self, actividad_id):
        r = self.client.post(f"/api/actividades/{actividad_id}/iniciar/")
        self.assertEqual(r.status_code, 201, r.content)
        return r.data

    def resolver(self, intento, bien=True, tiempo=5):
        for p in intento["preguntas"]:
            bp = BancoPregunta.objects.get(pk=p["id"])
            r = self.client.post(f"/api/intentos/{intento['id']}/responder/",
                                 {"pregunta": p["id"], "respuesta": self.correcta(bp) if bien else self.incorrecta(bp), "tiempo_segundos": tiempo}, format="json")
            self.assertEqual(r.status_code, 200, (bp.tipo, r.content))
        return self.client.post(f"/api/intentos/{intento['id']}/finalizar/")

    def actividad_de_un_tema(self, bien):
        a = self.generar(temas=[self.t1.id], num_preguntas=1, tipos_pregunta=["opcion_multiple"]).data
        return self.resolver(self.intento(a["id"]), bien=bien)

    # ---- generacion
    def test_generar_quiz_oculta_las_respuestas(self):
        r = self.generar()
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual((r.data["num_preguntas"], r.data["dificultad"], r.data["generada_por"]), (4, "media", "ia"))
        self.assertEqual(Counter(p["tema"] for p in r.data["preguntas"]), {self.t1.id: 2, self.t2.id: 2})
        self.assertTrue(all("respuesta_correcta" not in p and "explicacion" not in p for p in r.data["preguntas"]))
        self.assertEqual(BancoPregunta.objects.filter(origen="ia", validada=False).count(), 4)
        ini = self.intento(r.data["id"])
        self.assertEqual(ini["numero_intento"], 1)
        self.assertTrue(all("respuesta_correcta" not in p for p in ini["preguntas"]))

    def test_validaciones_al_generar(self):
        self.assertEqual(self.client.post("/api/actividades/generar/", {"materia": self.m.id, "temas": []}, format="json").status_code, 400)
        from apps.academico.models import Materia, Tema, Unidad
        otra = Materia.objects.create(nombre="Fisica")
        ajeno = Tema.objects.create(unidad=Unidad.objects.create(materia=otra, nombre="U"), nombre="Cinematica")
        self.assertEqual(self.generar(temas=[ajeno.id]).status_code, 400)           # tema de otra materia
        self.assertEqual(self.generar(num_preguntas=0).status_code, 400)
        self.assertEqual(self.generar(tipos_pregunta=["inventado"]).status_code, 400)

    def test_resolver_bien_los_siete_tipos_da_100_y_actualiza_progreso(self):
        a = self.generar(num_preguntas=14, tipos_pregunta=TODOS_LOS_TIPOS).data
        self.assertEqual(set(Counter(BancoPregunta.objects.values_list("tipo", flat=True))), set(TODOS_LOS_TIPOS))
        ini = self.intento(a["id"])
        self.assertEqual(self.client.post(f"/api/intentos/{ini['id']}/responder/", {"pregunta": ini["preguntas"][0]["id"], "respuesta": "x"}, format="json").data, {"guardada": True})
        r = self.resolver(ini)
        self.assertEqual((r.status_code, r.data["estado"], Decimal(str(r.data["calificacion"]))), (200, "finalizado", Decimal("100.00")), r.content)
        prog = Progreso.objects.get(usuario=self.ana, tema=self.t1)
        self.assertGreaterEqual(float(prog.probabilidad_dominio), 0.99)
        self.assertEqual((prog.nivel_dominio, prog.intentos_totales, prog.aciertos, prog.errores, prog.tiempo_total_segundos), ("dominado", 7, 7, 0, 35))
        det = self.client.get(f"/api/intentos/{ini['id']}/resultado/").data
        self.assertTrue(all(p["es_correcta"] and "respuesta_correcta" in p for p in det["preguntas"]))      # RF-33
        self.assertEqual(self.client.get("/api/progreso/?tema=%d" % self.t1.id).data["results"][0]["tema_nombre"], "Fotosintesis")

    def test_ejercicio_da_retroalimentacion_inmediata(self):
        a = self.generar(tipo="ejercicio", num_preguntas=2, tipos_pregunta=["opcion_multiple"]).data
        ini = self.intento(a["id"])
        p = ini["preguntas"][0]
        r = self.client.post(f"/api/intentos/{ini['id']}/responder/", {"pregunta": p["id"], "respuesta": "zzz"}, format="json")
        self.assertEqual((r.data["es_correcta"], r.data["puntaje"]), (False, 0.0))
        self.assertIn("Respuesta esperada", r.data["retroalimentacion"])

    def test_calificacion_por_tipo(self):
        def pregunta(tipo, correcta, **kw):
            return BancoPregunta(tema=self.t1, tipo=tipo, enunciado="?", respuesta_correcta=correcta, dificultad="media", **kw)
        c = lambda p, r: ev.calificar(p, r, self.ana)[:2]
        self.assertEqual(c(pregunta("verdadero_falso", "verdadero"), "V"), (True, 1.0))
        self.assertEqual(c(pregunta("verdadero_falso", "verdadero"), "falso"), (False, 0.0))
        self.assertEqual(c(pregunta("opcion_multiple", "b"), " B "), (True, 1.0))
        self.assertEqual(c(pregunta("completar_espacios", '["Fotosíntesis","Calvin"]'), ["fotosintesis", "x"]), (False, 0.5))   # acentos y mayusculas no importan
        self.assertEqual(c(pregunta("relacion_columnas", '{"1":"b","2":"a"}'), {"1": "b", "2": "a"}), (True, 1.0))
        self.assertEqual(c(pregunta("relacion_columnas", '{"1":"b","2":"a"}'), {"1": "b", "2": "c"}), (False, 0.5))
        self.assertEqual(c(pregunta("problema_matematico", "3.14"), "3,14"), (True, 1.0))
        self.assertEqual(c(pregunta("problema_matematico", "36"), "35"), (False, 0.0))
        self.assertEqual(c(pregunta("problema_matematico", "x = 2"), "X=2"), (True, 1.0))
        self.assertEqual(c(pregunta("completar_espacios", '["a"]'), "no es lista json {"), (False, 0.0))     # entrada rara no rompe

    # ---- tiempo, intentos e historial
    def test_el_servidor_valida_el_limite_de_tiempo(self):
        a = self.generar(limite_tiempo_min=1, num_preguntas=2, tipos_pregunta=["opcion_multiple"]).data
        ini = self.intento(a["id"])
        self.assertEqual(ini["limite_tiempo_min"], 1)
        Intento.objects.filter(pk=ini["id"]).update(fecha_inicio=timezone.now() - timedelta(minutes=5))
        r = self.client.post(f"/api/intentos/{ini['id']}/responder/", {"pregunta": ini["preguntas"][0]["id"], "respuesta": "a"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Intento.objects.get(pk=ini["id"]).estado, "expirado")
        self.assertEqual(self.client.post(f"/api/intentos/{ini['id']}/finalizar/").data["estado"], "expirado")

    def test_reintentos_e_historial(self):
        a = self.generar(num_preguntas=2, tipos_pregunta=["opcion_multiple"]).data
        i1 = self.intento(a["id"])
        self.assertEqual(self.client.get(f"/api/intentos/{i1['id']}/resultado/").status_code, 400)      # aun en curso
        self.assertEqual(self.intento(a["id"])["id"], i1["id"])                                          # retoma el abierto
        self.resolver(i1, bien=False)
        i2 = self.intento(a["id"])
        self.assertEqual(i2["numero_intento"], 2)
        self.resolver(i2, bien=True)
        h = self.client.get(f"/api/intentos/?actividad={a['id']}&ordering=-fecha_inicio").data
        self.assertEqual((h["count"], [float(x["calificacion"]) for x in h["results"]]), (2, [100.0, 0.0]))
        r = self.client.post(f"/api/intentos/{i2['id']}/responder/", {"pregunta": i2["preguntas"][0]["id"], "respuesta": "a"}, format="json")
        self.assertEqual(r.status_code, 400)                                                              # ya termino

    def test_actividades_son_privadas(self):
        a = self.generar().data
        ini = self.intento(a["id"])
        self.entrar(self.usuario("beto@mail.com"))
        for ruta in (f"/api/actividades/{a['id']}/", f"/api/intentos/{ini['id']}/", f"/api/intentos/{ini['id']}/resultado/"):
            self.assertEqual(self.client.get(ruta).status_code, 404, ruta)
        self.assertEqual(self.client.post(f"/api/intentos/{ini['id']}/finalizar/").status_code, 404)

    # ---- dificultad adaptativa y banco
    def test_dificultad_adaptativa_segun_el_dominio(self):
        Progreso.objects.create(usuario=self.ana, tema=self.t1, probabilidad_dominio=Decimal("0.9"), porcentaje=Decimal("90"), nivel_dominio="dominado")
        a = self.generar(adaptativa=True, num_preguntas=2).data
        self.assertEqual(a["dificultad"], "adaptativa")
        self.assertEqual(dict(BancoPregunta.objects.values_list("tema_id", "dificultad")), {self.t1.id: "alta", self.t2.id: "baja"})   # RF-29

    def test_banco_de_preguntas_de_docentes(self):
        docente = self.usuario("luis@mail.com", "docente")
        valida = {"tema": self.t1.id, "tipo": "opcion_multiple", "enunciado": "¿Donde ocurre la fotosintesis?", "dificultad": "media",
                  "opciones": [{"id": "a", "texto": "Cloroplasto"}, {"id": "b", "texto": "Nucleo"}], "respuesta_correcta": "a", "validada": True}
        self.assertEqual(self.client.post("/api/banco-preguntas/", valida, format="json").status_code, 403)         # estudiante
        self.entrar(docente)
        self.assertEqual(self.client.post("/api/banco-preguntas/", {**valida, "opciones": None}, format="json").status_code, 400)
        r = self.client.post("/api/banco-preguntas/", valida, format="json")
        self.assertEqual((r.status_code, r.data["origen"]), (201, "docente"), r.content)
        rel = self.client.post("/api/banco-preguntas/", {"tema": self.t1.id, "tipo": "completar_espacios", "enunciado": "Ocurre en el ___",
                                                         "dificultad": "media", "respuesta_correcta": ["cloroplasto"]}, format="json")
        self.assertEqual(json.loads(rel.data["respuesta_correcta"]), ["cloroplasto"])
        self.entrar(self.ana)                                                                                       # el estudiante usa la pregunta validada
        antes = BancoPregunta.objects.count()
        a = self.generar(temas=[self.t1.id], num_preguntas=1, tipos_pregunta=["opcion_multiple"]).data
        self.assertEqual((BancoPregunta.objects.count(), a["preguntas"][0]["id"]), (antes, r.data["id"]))

    # ---- diagnostico, recomendaciones, plan, metas
    def test_deteccion_de_dificultad_y_ciclo_de_recomendaciones(self):
        for _ in range(2):
            self.actividad_de_un_tema(bien=False)
        self.assertEqual(Dificultad.objects.count(), 0)                         # aun no hay 3 actividades con error
        self.actividad_de_un_tema(bien=False)
        dif = Dificultad.objects.get()
        self.assertEqual((dif.tema_id, dif.estado, dif.nivel, dif.errores_relevantes, dif.alerta_generada), (self.t1.id, "activa", "alta", 3, True))   # RF-22
        self.assertEqual(DificultadEvidencia.objects.filter(dificultad=dif).count(), 3)                          # RF-24
        self.assertEqual(len(self.client.get(f"/api/dificultades/{dif.id}/evidencias/").data), 3)
        self.assertEqual(Notificacion.objects.filter(usuario=self.ana, tipo="recomendacion").count(), 1)
        # recomendaciones (RF-37) sin duplicados
        recs = self.client.post("/api/recomendaciones/generar/").data
        self.assertEqual(sorted(r["tipo"] for r in recs), ["practicar_ejercicios", "repasar_tema"])
        self.assertEqual(self.client.post("/api/recomendaciones/generar/").data, [])
        # aceptar / rechazar (RF-39)
        a = self.client.patch(f"/api/recomendaciones/{recs[0]['id']}/", {"estado": "aceptada"}, format="json")
        self.assertEqual((a.status_code, a.data["estado"]), (200, "aceptada"))
        self.assertIsNotNone(a.data["fecha_respuesta"])
        self.assertEqual(self.client.patch(f"/api/recomendaciones/{recs[1]['id']}/", {"titulo": "otro", "tipo": "otro"}, format="json").data["titulo"], recs[1]["titulo"])
        # plan semanal (RF-38, RF-40)
        plan = self.client.post("/api/planes/generar/", {"tipo": "semanal", "dias": 7}, format="json")
        self.assertEqual((plan.status_code, plan.data["estado"], len(plan.data["items"])), (201, "propuesto", 2), plan.content)
        item = plan.data["items"][0]
        done = self.client.patch(f"/api/plan-items/{item['id']}/", {"completado": True}, format="json")
        self.assertTrue(done.data["completado"] and done.data["fecha_completado"])
        self.assertEqual(self.client.patch(f"/api/planes/{plan.data['id']}/", {"estado": "activo"}, format="json").data["estado"], "activo")
        # superar la dificultad al acertar de nuevo
        for _ in range(3):
            self.actividad_de_un_tema(bien=True)
        self.assertEqual(Dificultad.objects.get().estado, "superada")
        self.assertEqual(self.client.get("/api/dificultades/?estado=activa").data["count"], 0)

    def test_metas_medibles_se_actualizan_solas(self):
        r = self.client.post("/api/metas/", {"titulo": "Hacer 2 actividades", "indicador": "actividades_completadas", "valor_objetivo": "2", "valor_actual": "99"}, format="json")
        self.assertEqual((r.status_code, r.data["valor_actual"], r.data["estado"]), (201, "0.00", "activa"), r.content)       # el cliente no fija el avance
        self.actividad_de_un_tema(bien=True)
        self.assertEqual(Meta.objects.get().estado, "activa")
        self.actividad_de_un_tema(bien=True)
        m = Meta.objects.get()
        self.assertEqual((m.estado, m.valor_actual), ("cumplida", Decimal("2.00")))
        self.assertTrue(Notificacion.objects.filter(usuario=self.ana, tipo="avance").exists())

    def test_dashboard_y_exportes(self):
        self.client.post("/api/tareas/", {"titulo": "Entregar practica", "tipo": "entrega", "fecha_limite": (timezone.now() + timedelta(days=1)).isoformat()}, format="json")
        self.actividad_de_un_tema(bien=True)
        d = self.client.get("/api/dashboard/").data
        self.assertEqual((d["indicadores"]["actividades_realizadas"], d["indicadores"]["promedio_calificacion"], d["indicadores"]["tareas_pendientes"]), (1, 100.0, 1))
        self.assertEqual(d["progreso_por_materia"][0]["materia"], "Biologia")
        self.assertEqual(d["actividad_reciente"][0]["calificacion"], 100.0)
        xlsx = self.client.get("/api/dashboard/exportar/?formato=excel")
        self.assertEqual((xlsx.status_code, xlsx["Content-Type"][:30]), (200, "application/vnd.openxmlformats"))
        import openpyxl
        self.assertEqual(openpyxl.load_workbook(io.BytesIO(xlsx.content)).sheetnames, ["Resumen", "Por materia", "Dificultades", "Historial"])
        pdf = self.client.get("/api/dashboard/exportar/?formato=pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF") and pdf["Content-Type"] == "application/pdf")
        self.assertEqual(self.client.get("/api/dashboard/exportar/?formato=doc").status_code, 400)

    def test_docente_ve_el_progreso_de_sus_estudiantes(self):
        docente = self.usuario("luis@mail.com", "docente")
        UsuarioMateria.objects.create(usuario=docente, materia=self.m, relacion="imparte")
        UsuarioMateria.objects.create(usuario=self.ana, materia=self.m, relacion="cursa")
        self.actividad_de_un_tema(bien=True)
        self.assertEqual(self.client.get("/api/docente/estudiantes/").status_code, 403)
        self.entrar(docente)
        r = self.client.get("/api/docente/estudiantes/").data
        est = r[0]["estudiantes"][0]
        self.assertEqual((r[0]["nombre"], est["nombre"], est["temas_con_actividad"], est["dificultades_activas"]), ("Biologia", "Persona", 1, 0))
