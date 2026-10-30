"""Lectura de documentos (PDF, Word, PowerPoint, texto, imagenes) y division en fragmentos para el RAG."""
import io
import re


class ErrorExtraccion(Exception):
    pass


def extraer(tipo, datos):
    """Devuelve [(pagina_o_None, texto), ...]."""
    try:
        if tipo == "pdf":
            from pypdf import PdfReader
            return [(i + 1, p.extract_text() or "") for i, p in enumerate(PdfReader(io.BytesIO(datos)).pages)]
        if tipo == "docx":
            import docx
            d = docx.Document(io.BytesIO(datos))
            partes = [p.text for p in d.paragraphs]
            for tabla in d.tables:
                partes += [" | ".join(c.text for c in fila.cells) for fila in tabla.rows]
            return [(None, "\n".join(partes))]
        if tipo == "pptx":
            from pptx import Presentation
            salida = []
            for i, diap in enumerate(Presentation(io.BytesIO(datos)).slides):
                partes = [f.text_frame.text for f in diap.shapes if f.has_text_frame]
                salida.append((i + 1, "\n".join(partes)))
            return salida
        if tipo == "txt":
            return [(None, datos.decode("utf-8", errors="replace"))]
        if tipo in ("png", "jpg"):
            try:
                import pytesseract
                from PIL import Image
            except ImportError as e:
                raise ErrorExtraccion("OCR no disponible: instala tesseract-ocr y pytesseract para analizar imagenes") from e
            return [(None, pytesseract.image_to_string(Image.open(io.BytesIO(datos)), lang="spa+eng"))]
    except ErrorExtraccion:
        raise
    except Exception as e:
        raise ErrorExtraccion(f"No se pudo leer el archivo ({tipo}): {e}") from e
    raise ErrorExtraccion(f"Tipo de archivo no soportado: {tipo}")


def trocear(paginas, tamano=900, solape=150):
    """Divide el texto en fragmentos de ~'tamano' caracteres con solape. Devuelve [(orden, pagina, texto), ...]."""
    trozos, orden = [], 0
    for pagina, texto in paginas:
        texto = re.sub(r"\s+", " ", texto or "").strip()
        i = 0
        while i < len(texto):
            fin = min(len(texto), i + tamano)
            if fin < len(texto):
                corte = max(texto.rfind(". ", i, fin), texto.rfind(" ", i, fin))
                if corte > i + tamano // 2:
                    fin = corte + 1
            pedazo = texto[i:fin].strip()
            if pedazo:
                trozos.append((orden, pagina, pedazo))
                orden += 1
            if fin >= len(texto):
                break
            i = fin - solape if fin - solape > i else fin
    return trozos
