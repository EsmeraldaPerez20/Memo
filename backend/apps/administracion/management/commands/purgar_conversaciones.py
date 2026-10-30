from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.tutor.models import Conversacion


class Command(BaseCommand):
    help = "Borra las conversaciones que el estudiante NO autorizo guardar (guardada = false) tras N horas sin actividad (RF-10, RF-11)."

    def add_arguments(self, parser):
        parser.add_argument("--horas", type=int, default=24)

    def handle(self, *args, horas, **opts):
        limite = timezone.now() - timedelta(hours=horas)
        n, _ = Conversacion.objects.filter(guardada=False, fecha_ultima_actividad__lt=limite).delete()
        self.stdout.write(self.style.SUCCESS(f"{n} conversaciones sin consentimiento eliminadas."))
