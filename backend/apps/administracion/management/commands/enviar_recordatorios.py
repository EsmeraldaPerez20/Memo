from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.administracion.models import Notificacion
from apps.planificacion.models import Tarea
from servicios import notificaciones


class Command(BaseCommand):
    help = "Avisa de las tareas que vencen en las proximas N horas (RF-54). Programalo con un cron (cada hora)."

    def add_arguments(self, parser):
        parser.add_argument("--horas", type=int, default=24)

    def handle(self, *args, horas, **opts):
        ahora = timezone.now()
        enviados = 0
        for t in Tarea.objects.filter(completada=False, fecha_limite__gt=ahora, fecha_limite__lte=ahora + timedelta(hours=horas)).select_related("usuario"):
            titulo = f"Recordatorio: {t.titulo}"
            if Notificacion.objects.filter(usuario=t.usuario, tipo="recordatorio", titulo=titulo).exists():
                continue       # ya se aviso
            notificaciones.notificar(t.usuario, "recordatorio", titulo, f"Vence el {timezone.localtime(t.fecha_limite):%d/%m a las %H:%M}.")
            enviados += 1
        self.stdout.write(self.style.SUCCESS(f"{enviados} recordatorios enviados."))
