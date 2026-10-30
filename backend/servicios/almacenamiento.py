"""Almacenamiento PRIVADO de archivos (RF-19). En produccion: bucket privado de Supabase Storage.
Sin SUPABASE_URL (desarrollo) guarda en una carpeta local que nunca se sirve publicamente."""
import re
import uuid

import requests
from django.conf import settings


class AlmacenamientoError(Exception):
    pass


def _remoto():
    return bool(settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY)


def _cabeceras(extra=None):
    h = {"Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}", "apikey": settings.SUPABASE_SERVICE_KEY}
    h.update(extra or {})
    return h


def _url(ruta, prefijo="object"):
    return f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/{prefijo}/{settings.SUPABASE_BUCKET}/{ruta}"


def nombre_seguro(nombre):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", nombre)[-120:] or "archivo"


def ruta_nueva(usuario_id, nombre):
    return f"{usuario_id}/{uuid.uuid4().hex}-{nombre_seguro(nombre)}"


def _local(ruta):
    destino = (settings.ALMACENAMIENTO_LOCAL / ruta).resolve()
    if settings.ALMACENAMIENTO_LOCAL.resolve() not in destino.parents:
        raise AlmacenamientoError("Ruta no permitida")
    return destino


def guardar(ruta, datos, content_type="application/octet-stream"):
    if _remoto():
        r = requests.post(_url(ruta), headers=_cabeceras({"Content-Type": content_type, "x-upsert": "false"}), data=datos, timeout=60)
        if not r.ok:
            raise AlmacenamientoError(f"No se pudo guardar el archivo ({r.status_code})")
        return
    destino = _local(ruta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(datos)


def leer(ruta):
    if _remoto():
        r = requests.get(_url(ruta, "object/authenticated"), headers=_cabeceras(), timeout=60)
        if not r.ok:
            raise AlmacenamientoError(f"No se pudo leer el archivo ({r.status_code})")
        return r.content
    try:
        return _local(ruta).read_bytes()
    except FileNotFoundError as e:
        raise AlmacenamientoError("El archivo no existe en el almacenamiento") from e


def eliminar(ruta):
    """Borra el archivo (RF-20). Si ya no existe no es un error."""
    if _remoto():
        r = requests.delete(_url(ruta), headers=_cabeceras(), timeout=30)
        if not r.ok and r.status_code != 404:
            raise AlmacenamientoError(f"No se pudo eliminar el archivo ({r.status_code})")
        return
    try:
        _local(ruta).unlink()
    except FileNotFoundError:
        pass


def url_temporal(ruta, segundos=300):
    """Enlace firmado de corta duracion (Supabase). En local devuelve None: se descarga por la API."""
    if not _remoto():
        return None
    r = requests.post(_url(ruta, "object/sign"), headers=_cabeceras({"Content-Type": "application/json"}),
                      json={"expiresIn": segundos}, timeout=30)
    if not r.ok:
        raise AlmacenamientoError(f"No se pudo firmar el enlace ({r.status_code})")
    return settings.SUPABASE_URL.rstrip("/") + "/storage/v1" + r.json()["signedURL"]
