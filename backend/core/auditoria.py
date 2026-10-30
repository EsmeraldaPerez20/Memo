def ip_de(request):
    if request is None:
        return None
    reenviada = request.META.get("HTTP_X_FORWARDED_FOR")
    return reenviada.split(",")[0].strip() if reenviada else request.META.get("REMOTE_ADDR")


def registrar(request, accion, usuario=None, entidad=None, entidad_id=None, detalle=None):
    """Guarda un evento en bitacora_auditoria (RF-51). Nunca debe guardarse una contrasena en 'detalle'."""
    from apps.administracion.models import BitacoraAuditoria
    if usuario is None and request is not None and getattr(request, "user", None) and request.user.is_authenticated:
        usuario = request.user
    return BitacoraAuditoria.objects.create(usuario=usuario, accion=accion, entidad=entidad,
                                            entidad_id=entidad_id, detalle=detalle, ip=ip_de(request))
