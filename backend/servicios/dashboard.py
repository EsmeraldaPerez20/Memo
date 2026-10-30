"""Dashboard del estudiante (RF-42 a RF-44) y exportacion de reportes (RF-45)."""
import io

from django.db import connection


def _filas(sql, params):
    with connection.cursor() as c:
        c.execute(sql, params)
        nombres = [col[0] for col in c.description]
        return [dict(zip(nombres, f)) for f in c.fetchall()]


def _num(x):
    return float(x) if x is not None else None


def resumen(usuario):
    from apps.diagnostico.models import Dificultad
    from apps.evaluaciones.models import Intento
    from apps.planificacion.models import Meta, Recomendacion, Tarea
    kpi = (_filas("SELECT temas_dominados, dificultades_activas, promedio_calificacion, actividades_realizadas, "
                  "tiempo_total_segundos, tareas_pendientes FROM v_dashboard_estudiante WHERE usuario_id = %s", [usuario.id])
           or [{"temas_dominados": 0, "dificultades_activas": 0, "promedio_calificacion": None, "actividades_realizadas": 0,
                "tiempo_total_segundos": 0, "tareas_pendientes": 0}])[0]
    kpi["promedio_calificacion"] = _num(kpi["promedio_calificacion"])
    materias = _filas("SELECT materia_id, materia, porcentaje_promedio, temas_dominados, temas_con_actividad "
                      "FROM v_progreso_por_materia WHERE usuario_id = %s ORDER BY materia", [usuario.id])
    for m in materias:
        m["porcentaje_promedio"] = _num(m["porcentaje_promedio"])
    return {
        "indicadores": kpi,
        "progreso_por_materia": materias,
        "dificultades_activas": [{"id": d.id, "tema": d.tema.nombre, "nivel": d.nivel, "errores_relevantes": d.errores_relevantes}
                                 for d in Dificultad.objects.filter(usuario=usuario, estado="activa").select_related("tema")],
        "recomendaciones_pendientes": [{"id": r.id, "titulo": r.titulo, "tipo": r.tipo, "prioridad": r.prioridad}
                                       for r in Recomendacion.objects.filter(usuario=usuario, estado="pendiente")[:5]],
        "tareas_pendientes": [{"id": t.id, "titulo": t.titulo, "tipo": t.tipo, "fecha_limite": t.fecha_limite}
                              for t in Tarea.objects.filter(usuario=usuario, completada=False).order_by("fecha_limite")[:5]],
        "actividad_reciente": [{"id": i.id, "actividad": i.actividad.titulo, "calificacion": _num(i.calificacion), "estado": i.estado,
                                "fecha": i.fecha_inicio} for i in Intento.objects.filter(usuario=usuario).select_related("actividad").order_by("-id")[:5]],
        "metas_activas": [{"id": m.id, "titulo": m.titulo, "indicador": m.indicador, "objetivo": _num(m.valor_objetivo), "actual": _num(m.valor_actual)}
                          for m in Meta.objects.filter(usuario=usuario, estado="activa")],
    }


def historial(usuario):
    from apps.evaluaciones.models import Intento
    return [[i.fecha_inicio.strftime("%Y-%m-%d %H:%M"), i.actividad.titulo, i.estado, _num(i.calificacion), i.tiempo_segundos or 0]
            for i in Intento.objects.filter(usuario=usuario).select_related("actividad").order_by("-id")]


def a_excel(usuario):
    from openpyxl import Workbook
    from openpyxl.styles import Font
    d = resumen(usuario)
    wb = Workbook()
    ws = wb.active
    ws.title = "Resumen"
    ws.append(["Reporte de progreso", usuario.get_full_name()])
    for k, v in d["indicadores"].items():
        ws.append([k.replace("_", " ").capitalize(), v])
    ws2 = wb.create_sheet("Por materia")
    ws2.append(["Materia", "Avance promedio %", "Temas dominados", "Temas con actividad"])
    for m in d["progreso_por_materia"]:
        ws2.append([m["materia"], m["porcentaje_promedio"], m["temas_dominados"], m["temas_con_actividad"]])
    ws3 = wb.create_sheet("Dificultades")
    ws3.append(["Tema", "Nivel", "Errores relevantes"])
    for x in d["dificultades_activas"]:
        ws3.append([x["tema"], x["nivel"], x["errores_relevantes"]])
    ws4 = wb.create_sheet("Historial")
    ws4.append(["Fecha", "Actividad", "Estado", "Calificacion", "Segundos"])
    for fila in historial(usuario):
        ws4.append(fila)
    for hoja in wb.worksheets:
        for celda in hoja[1]:
            celda.font = Font(bold=True)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def a_pdf(usuario):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    d, est, buf = resumen(usuario), getSampleStyleSheet(), io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, title="Reporte de progreso")

    def tabla(filas):
        t = Table(filas, repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#965F99")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                               ("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 9)]))
        return t
    partes = [Paragraph("Memo - Reporte de progreso", est["Title"]), Paragraph(f"Estudiante: {usuario.get_full_name()}", est["Normal"]), Spacer(1, 12)]
    partes.append(tabla([["Indicador", "Valor"]] + [[k.replace("_", " ").capitalize(), str(v)] for k, v in d["indicadores"].items()]))
    partes += [Spacer(1, 14), Paragraph("Avance por materia", est["Heading2"])]
    partes.append(tabla([["Materia", "Avance %", "Dominados"]] + [[m["materia"], str(m["porcentaje_promedio"]), str(m["temas_dominados"])] for m in d["progreso_por_materia"]]))
    partes += [Spacer(1, 14), Paragraph("Dificultades activas", est["Heading2"])]
    partes.append(tabla([["Tema", "Nivel", "Errores"]] + [[x["tema"], x["nivel"], str(x["errores_relevantes"])] for x in d["dificultades_activas"]]))
    doc.build(partes)
    return buf.getvalue()
