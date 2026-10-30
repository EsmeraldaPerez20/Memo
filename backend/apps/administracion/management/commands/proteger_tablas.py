from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = ("Activa RLS en TODAS las tablas del esquema public (incluidas las que crea Django). "
            "Ejecutalo despues de cada 'migrate': Supabase expone por API publica las tablas sin RLS.")

    def handle(self, *args, **opts):
        with connection.cursor() as c:
            c.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND NOT rowsecurity")
            pendientes = [r[0] for r in c.fetchall()]
            for t in pendientes:
                c.execute(f'ALTER TABLE public."{t}" ENABLE ROW LEVEL SECURITY')
        self.stdout.write(self.style.SUCCESS(f"RLS activado en {len(pendientes)} tablas nuevas."))
