"""Notificaciones (RF-54): respetan las preferencias de cada usuario (tipos y canales)."""
import logging

from django.core.mail import send_mail
from django.utils import timezone

log = logging.getLogger(__name__)

PREFERENCIA_DE = {
    "recomendacion": "notif_recomendaciones", "recordatorio": "notif_recordatorios",
    "resultado": "notif_resultados", "material": "notif_materiales", "avance": "notif_avances",
}


def notificar(usuario, tipo, titulo, mensaje=""):
    """Crea una notificacion por cada canal activo del usuario. Devuelve la lista creada."""
    from apps.administracion.models import Notificacion
    from apps.usuarios.models import PreferenciaUsuario
    pref = PreferenciaUsuario.objects.filter(usuario=usuario).first()
    if pref is not None and not getattr(pref, PREFERENCIA_DE[tipo]):
        return []
    canales = ["app"] if (pref is None or pref.canal_app) else []
    if pref is not None and pref.canal_correo:
        canales.append("correo")
    if pref is not None and pref.canal_whatsapp and usuario.telefono:
        canales.append("whatsapp")
    creadas = []
    for canal in canales:
        n = Notificacion.objects.create(usuario=usuario, tipo=tipo, titulo=titulo, mensaje=mensaje, canal=canal)
        if canal == "app":
            n.fecha_envio = timezone.now()
            n.save(update_fields=["fecha_envio"])
        elif canal == "correo":
            try:
                send_mail(titulo, mensaje or titulo, None, [usuario.correo])
                n.fecha_envio = timezone.now()
                n.save(update_fields=["fecha_envio"])
            except Exception:
                log.exception("No se pudo enviar el correo a %s", usuario.correo)
        # whatsapp: queda pendiente (fecha_envio NULL) hasta conectar un proveedor (Twilio / Meta Cloud API)
        creadas.append(n)
    return creadas
