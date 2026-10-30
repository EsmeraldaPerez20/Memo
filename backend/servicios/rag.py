"""RAG: convierte documentos y materiales en fragmentos con embeddings y busca los mas relevantes."""
import re
from collections import Counter

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from pgvector.django import CosineDistance

from . import almacenamiento, ia, texto


def _trozos(archivo_url, tipo):
    paginas = texto.extraer(tipo, almacenamiento.leer(archivo_url))
    trozos = texto.trocear(paginas)
    if not trozos:
        raise texto.ErrorExtraccion("El archivo no contiene texto que se pueda analizar")
    return trozos


def indexar_documento(doc, usuario):
    """Lee el documento, guarda sus fragmentos con embeddings y genera el analisis (RF-15, RF-16, RF-18)."""
    from apps.documentos.models import Fragmento
    doc.estado_analisis = "procesando"
    doc.save(update_fields=["estado_analisis"])
    try:
        trozos = _trozos(doc.archivo_url, doc.tipo_archivo)
        vectores = ia.embeddings([t for _, _, t in trozos], usuario)
        with transaction.atomic():
            Fragmento.objects.filter(documento=doc).delete()
            Fragmento.objects.bulk_create([
                Fragmento(documento=doc, orden=o, num_pagina=p, contenido=t, embedding=v)
                for (o, p, t), v in zip(trozos, vectores)])
        analizar_documento(doc, " ".join(t for _, _, t in trozos), usuario)
        doc.estado_analisis, doc.fecha_analisis = "completado", timezone.now()
        doc.save(update_fields=["estado_analisis", "fecha_analisis"])
    except Exception:
        doc.estado_analisis = "error"
        doc.save(update_fields=["estado_analisis"])
        raise
    return len(trozos)


def indexar_material(material, usuario):
    """Indexa un material aprobado por el docente para que el tutor lo use (RF-47, RNF-24)."""
    from apps.documentos.models import Fragmento
    trozos = _trozos(material.archivo_url, material.tipo_archivo)
    vectores = ia.embeddings([t for _, _, t in trozos], usuario)
    with transaction.atomic():
        Fragmento.objects.filter(material=material).delete()
        Fragmento.objects.bulk_create([
            Fragmento(material=material, orden=o, num_pagina=p, contenido=t, embedding=v)
            for (o, p, t), v in zip(trozos, vectores)])
    return len(trozos)


# ------------------------------------------------------------------ analisis automatico del documento
def _analisis_simulado(t):
    comunes = [w for w, _ in Counter(ia.tokens(t, 5)).most_common(8)]
    oraciones = re.split(r"(?<=[.!?])\s+", t)

    def frase(w):
        return next((o for o in oraciones if w in ia.normalizar(o)), "")[:220]
    return {
        "resumen": " ".join(oraciones[:3])[:600],
        "conceptos": [{"termino": w, "descripcion": frase(w)} for w in comunes[:3]],
        "definiciones": [{"termino": w, "definicion": frase(w)} for w in comunes[:2]],
        "palabras_clave": comunes,
        "preguntas": [f"¿Que es {w}?" for w in comunes[:3]],
        "ejercicios": [f"Explica con tus palabras {w}." for w in comunes[:2]],
        "tema_sugerido": comunes[0] if comunes else "",
    }


def analizar_documento(doc, texto_completo, usuario):
    from apps.academico.models import Tema
    from apps.documentos.models import DocumentoTema, ElementoDocumento
    muestra = texto_completo[:12000]
    prompt = ('Analiza este texto academico y devuelve un JSON con las claves: "resumen" (maximo 120 palabras), '
              '"conceptos" (lista de {"termino","descripcion"}), "definiciones" (lista de {"termino","definicion"}), '
              '"palabras_clave" (lista de textos), "preguntas" (lista de textos), "ejercicios" (lista de textos) y '
              '"tema_sugerido" (nombre corto del tema principal).\n\nTEXTO:\n' + muestra)
    datos = ia.completar_json(prompt, "Eres un asistente academico que analiza apuntes de universitarios y responde en espanol.",
                              "analisis_documento", usuario, simulacion=lambda: _analisis_simulado(muestra))
    filas = [ElementoDocumento(documento=doc, tipo="resumen", titulo="Resumen", contenido=str(datos.get("resumen", ""))[:5000])]
    for c in datos.get("conceptos", []):
        filas.append(ElementoDocumento(documento=doc, tipo="concepto", titulo=str(c.get("termino", ""))[:200], contenido=str(c.get("descripcion", ""))))
    for d in datos.get("definiciones", []):
        filas.append(ElementoDocumento(documento=doc, tipo="definicion", titulo=str(d.get("termino", ""))[:200], contenido=str(d.get("definicion", ""))))
    for tipo, clave in (("palabra_clave", "palabras_clave"), ("pregunta", "preguntas"), ("ejercicio", "ejercicios")):
        filas += [ElementoDocumento(documento=doc, tipo=tipo, contenido=str(x)) for x in datos.get(clave, [])]
    sugerido = str(datos.get("tema_sugerido") or "").strip()
    if sugerido:
        filas.append(ElementoDocumento(documento=doc, tipo="tema", titulo="Tema sugerido", contenido=sugerido))
    with transaction.atomic():
        ElementoDocumento.objects.filter(documento=doc).delete()
        ElementoDocumento.objects.bulk_create([f for f in filas if f.contenido.strip()])
        if sugerido:
            temas = Tema.objects.filter(nombre__icontains=sugerido)
            if doc.materia_id:
                temas = temas.filter(unidad__materia_id=doc.materia_id)
            tema = temas.first()
            if tema and not DocumentoTema.objects.filter(documento=doc, tema=tema).exists():
                DocumentoTema.objects.create(documento=doc, tema=tema, sugerido_por_ia=True, confirmado=False)


# ------------------------------------------------------------------ busqueda semantica
def buscar(usuario, consulta, documento=None, materia=None, k=None):
    """Fragmentos mas parecidos a la consulta: [(fragmento, distancia, 'documento'|'material'), ...].
    Solo busca en lo que el usuario puede ver: sus documentos (RF-19) y materiales aprobados de sus materias (RF-47).
    Los materiales validados por docentes tienen prioridad (RNF-24)."""
    from apps.academico.models import UsuarioMateria
    from apps.documentos.models import Fragmento
    k = k or settings.RAG_TOP_K
    vector = ia.embedding(consulta, usuario)
    base = Fragmento.objects.filter(embedding__isnull=False).select_related("documento", "material")
    if documento is not None:
        propios = base.filter(documento=documento, documento__fecha_eliminacion__isnull=True)
    else:
        propios = base.filter(documento__usuario=usuario, documento__fecha_eliminacion__isnull=True)
        if materia is not None:
            propios = propios.filter(documento__materia=materia)
    res = [(f, float(f.dist), "documento") for f in propios.annotate(dist=CosineDistance("embedding", vector)).order_by("dist")[:k]]
    if documento is None:
        mats = base.filter(material__estado="aprobado")
        if materia is not None:
            mats = mats.filter(material__materia=materia)
        elif not usuario.es_administrador:
            ids = list(UsuarioMateria.objects.filter(usuario=usuario).values_list("materia_id", flat=True))
            mats = mats.filter(material__materia_id__in=ids)
        res += [(f, float(f.dist), "material") for f in mats.annotate(dist=CosineDistance("embedding", vector)).order_by("dist")[:k]]
    res.sort(key=lambda r: r[1] - (0.05 if r[2] == "material" else 0.0))
    return res[:k]
