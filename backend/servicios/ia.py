"""Capa unica de acceso a la IA (modelo de lenguaje + embeddings).

El resto del backend NUNCA llama a un proveedor directamente: todo pasa por aqui, asi se cambia de
proveedor con una variable de entorno y cada llamada queda registrada en consumo_ia (RNF-25).

IA_PROVEEDOR = simulado | anthropic | openai        (por defecto: simulado, no necesita claves)
"""
import hashlib
import json
import math
import re
import time
import unicodedata
from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings


class IAError(Exception):
    """Error al usar el servicio de IA: falta la clave, el proveedor fallo o la respuesta no es valida."""


@dataclass
class RespuestaIA:
    texto: str
    tokens_entrada: int = 0
    tokens_salida: int = 0
    modelo: str = ""
    proveedor: str = ""
    duracion_ms: int = 0
    consumo: object = None      # fila de consumo_ia; el tutor la enlaza al mensaje despues de crearlo


MODELOS_DEFECTO = {"anthropic": "claude-haiku-5-5", "openai": "gpt-4o-mini"}


# ------------------------------------------------------------------ utilidades de texto
def normalizar(texto):
    texto = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return texto.lower()


def tokens(texto, minimo=3):
    return re.findall(r"[a-z0-9]{%d,}" % minimo, normalizar(texto))


def extraer_json(texto):
    """Obtiene el JSON de la respuesta de un modelo (quita ```json ... ``` y texto alrededor)."""
    t = (texto or "").strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    inicio = min([i for i in (t.find("{"), t.find("[")) if i >= 0], default=-1)
    if inicio > 0:
        t = t[inicio:]
    try:
        return json.loads(t)
    except ValueError:
        pass
    fin = max(t.rfind("}"), t.rfind("]"))
    try:
        return json.loads(t[: fin + 1])
    except ValueError as e:
        raise IAError("La IA no devolvio un JSON valido") from e


# ------------------------------------------------------------------ modelo de lenguaje
def _modelo():
    return settings.IA_MODELO or MODELOS_DEFECTO.get(settings.IA_PROVEEDOR, "simulado")


def _registrar(resp, funcion, usuario):
    from apps.administracion.models import ConsumoIA
    costo = (resp.tokens_entrada * settings.IA_PRECIO_ENTRADA_USD_POR_M
             + resp.tokens_salida * settings.IA_PRECIO_SALIDA_USD_POR_M) / 1_000_000
    return ConsumoIA.objects.create(
        usuario=usuario, funcion=funcion, proveedor=resp.proveedor, modelo=resp.modelo,
        tokens_entrada=resp.tokens_entrada, tokens_salida=resp.tokens_salida,
        costo_estimado=Decimal(str(round(costo, 6))), duracion_ms=resp.duracion_ms)


def completar(mensajes, system="", funcion="tutor", usuario=None, max_tokens=1200, simulacion=None):
    """Pide una respuesta al modelo. 'mensajes' = [{'role': 'user'|'assistant', 'content': '...'}].
    'simulacion' es una funcion sin argumentos que produce el texto cuando IA_PROVEEDOR=simulado."""
    proveedor = settings.IA_PROVEEDOR
    t0 = time.monotonic()
    if proveedor == "simulado":
        texto = simulacion() if simulacion else "Respuesta simulada."
        tin, tout, modelo = sum(len(m["content"]) for m in mensajes) // 4, len(texto) // 4, "simulado"
    elif proveedor == "anthropic":
        try:
            import anthropic
        except ImportError as e:
            raise IAError("Falta instalar el paquete 'anthropic' (pip install anthropic)") from e
        if not settings.ANTHROPIC_API_KEY:
            raise IAError("Falta la variable ANTHROPIC_API_KEY")
        kwargs = dict(model=_modelo(), max_tokens=max_tokens, messages=mensajes)
        if system:
            kwargs["system"] = system
        try:
            r = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=60).messages.create(**kwargs)
        except Exception as e:
            raise IAError(f"Error del proveedor de IA: {e}") from e
        texto = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
        tin, tout, modelo = r.usage.input_tokens, r.usage.output_tokens, r.model
    elif proveedor == "openai":
        try:
            import openai
        except ImportError as e:
            raise IAError("Falta instalar el paquete 'openai' (pip install openai)") from e
        if not settings.OPENAI_API_KEY:
            raise IAError("Falta la variable OPENAI_API_KEY")
        msgs = ([{"role": "system", "content": system}] if system else []) + list(mensajes)
        try:
            r = openai.OpenAI(api_key=settings.OPENAI_API_KEY, timeout=60).chat.completions.create(
                model=_modelo(), messages=msgs, max_tokens=max_tokens)
        except Exception as e:
            raise IAError(f"Error del proveedor de IA: {e}") from e
        texto = r.choices[0].message.content or ""
        tin, tout, modelo = r.usage.prompt_tokens, r.usage.completion_tokens, r.model
    else:
        raise IAError(f"IA_PROVEEDOR desconocido: {proveedor}")
    resp = RespuestaIA(texto=texto, tokens_entrada=tin, tokens_salida=tout, modelo=modelo, proveedor=proveedor,
                       duracion_ms=int((time.monotonic() - t0) * 1000))
    resp.consumo = _registrar(resp, funcion, usuario)
    return resp


def completar_json(prompt, system="", funcion="otro", usuario=None, max_tokens=2000, simulacion=None):
    """Igual que completar(), pero devuelve el JSON ya convertido en objeto de Python."""
    sim = (lambda: json.dumps(simulacion(), ensure_ascii=False)) if simulacion else None
    resp = completar([{"role": "user", "content": prompt}],
                     system=(system + "\nResponde UNICAMENTE con JSON valido, sin texto adicional.").strip(),
                     funcion=funcion, usuario=usuario, max_tokens=max_tokens, simulacion=sim)
    return extraer_json(resp.texto)


# ------------------------------------------------------------------ embeddings (busqueda semantica del RAG)
PALABRAS_VACIAS = {"que", "los", "las", "del", "con", "por", "para", "una", "uno", "unos", "unas", "como", "mas", "pero", "sus", "este",
                   "esta", "esto", "ese", "esa", "son", "fue", "ser", "hay", "cual", "cuales", "donde", "cuando", "quien", "entre",
                   "sobre", "desde", "hasta", "tambien", "muy", "sin", "nos", "les", "the", "and"}


def _embedding_simulado(texto):
    """Vector determinista por palabras (bolsa de palabras hasheada). Sirve para probar todo el RAG sin proveedor."""
    dim = settings.EMBEDDING_DIM
    v = [0.0] * dim
    for tok in tokens(texto):
        if tok in PALABRAS_VACIAS:
            continue
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        v[h % dim] += 1.0 if (h >> 40) & 1 else -1.0
    norma = math.sqrt(sum(x * x for x in v))
    if norma == 0:
        v[0], norma = 1.0, 1.0
    return [x / norma for x in v]


def embeddings(textos, usuario=None):
    """Devuelve un vector (lista de floats) por cada texto."""
    if settings.EMBEDDINGS_PROVEEDOR == "simulado":
        return [_embedding_simulado(t) for t in textos]
    if settings.EMBEDDINGS_PROVEEDOR == "openai":
        try:
            import openai
        except ImportError as e:
            raise IAError("Falta instalar el paquete 'openai' (pip install openai)") from e
        if not settings.OPENAI_API_KEY:
            raise IAError("Falta la variable OPENAI_API_KEY para los embeddings")
        t0 = time.monotonic()
        salida, tokens_usados = [], 0
        try:
            cliente = openai.OpenAI(api_key=settings.OPENAI_API_KEY, timeout=60)
            for i in range(0, len(textos), 64):
                r = cliente.embeddings.create(model=settings.EMBEDDING_MODELO, input=textos[i:i + 64])
                salida += [d.embedding for d in r.data]
                tokens_usados += r.usage.total_tokens
        except Exception as e:
            raise IAError(f"Error al generar embeddings: {e}") from e
        resp = RespuestaIA(texto="", tokens_entrada=tokens_usados, modelo=settings.EMBEDDING_MODELO, proveedor="openai",
                           duracion_ms=int((time.monotonic() - t0) * 1000))
        _registrar(resp, "embeddings", usuario)
        return salida
    raise IAError(f"EMBEDDINGS_PROVEEDOR desconocido: {settings.EMBEDDINGS_PROVEEDOR}")


def embedding(texto, usuario=None):
    return embeddings([texto], usuario)[0]
