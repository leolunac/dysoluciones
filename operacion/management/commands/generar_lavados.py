from django.core.management.base import BaseCommand
from django.utils import timezone
from dateutil.relativedelta import relativedelta

from operacion.models import Cliente, LavadoTanque


class Command(BaseCommand):
    help = "Genera programaciones de lavado de tanque para clientes según frecuencia (4 o 6 meses)."

    def handle(self, *args, **options):
        hoy = timezone.now().date()
        creados = 0
        revisados = 0

        for c in Cliente.objects.filter(activo=True):
            revisados += 1

            # Si no hay fecha último lavado, usamos hoy como base (para no bloquear)
            base = c.fecha_ultimo_lavado or hoy

            # Próxima fecha programada
            proxima = base + relativedelta(months=int(c.frecuencia_lavado))

            # Crear solo si no existe ya
            obj, created = LavadoTanque.objects.get_or_create(
                cliente=c,
                fecha_programada=proxima,
            )
            if created:
                creados += 1

        self.stdout.write(self.style.SUCCESS(
            f"Clientes revisados: {revisados} | Programaciones creadas: {creados}"
        ))
from django.core.management.base import BaseCommand
from django.utils import timezone
from dateutil.relativedelta import relativedelta

from operacion.models import Cliente, LavadoTanque


class Command(BaseCommand):

    help = "Genera programaciones de lavado de tanques automáticamente"

    def handle(self, *args, **kwargs):

        hoy = timezone.now().date()

        for cliente in Cliente.objects.filter(activo=True):

            if not cliente.fecha_ultimo_lavado:
                continue

            proxima_fecha = cliente.fecha_ultimo_lavado + relativedelta(
                months=cliente.frecuencia_lavado
            )

            LavadoTanque.objects.get_or_create(
                cliente=cliente,
                fecha_programada=proxima_fecha
            )

        self.stdout.write(self.style.SUCCESS("Lavados generados correctamente"))        