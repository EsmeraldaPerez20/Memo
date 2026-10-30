def obtener(clave, defecto=None):
    """Lee un parametro de configuraciones_sistema (RF-49). El valor es JSON: 20, "texto", etc."""
    from apps.administracion.models import ConfiguracionSistema
    fila = ConfiguracionSistema.objects.filter(pk=clave).first()
    return fila.valor if fila is not None else defecto
