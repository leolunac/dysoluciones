from dateutil.relativedelta import relativedelta
from django.core.management.base import BaseCommand

from operacion.models import Cliente, LavadoTanque


class Command(BaseCommand):
    help = "Propone el próximo lavado solo para unidades con una ejecución real anterior."

    def add_arguments(self, parser):
        parser.add_argument(
            "--aplicar",
            action="store_true",
            help="Crea las programaciones propuestas. Sin esta opción solo simula.",
        )

    def handle(self, *args, **options):
        aplicar = options["aplicar"]
        candidatos = Cliente.objects.filter(
            activo=True,
            fecha_ultimo_lavado__isnull=False,
        ).order_by("nombre")
        propuestas = []
        omitidos = 0

        for cliente in candidatos:
            if LavadoTanque.objects.filter(cliente=cliente, ejecutado=False).exists():
                omitidos += 1
                continue
            proxima = cliente.fecha_ultimo_lavado + relativedelta(
                months=int(cliente.frecuencia_lavado)
            )
            propuestas.append((cliente, proxima))

        self.stdout.write("=" * 64)
        self.stdout.write("SIMULACIÓN DE PROGRAMACIÓN DE LAVADOS")
        self.stdout.write("=" * 64)
        self.stdout.write(f"Unidades con último lavado real: {candidatos.count()}")
        self.stdout.write(f"Programaciones propuestas: {len(propuestas)}")
        self.stdout.write(f"Omitidas por tener una programación pendiente: {omitidos}")

        if not aplicar:
            self.stdout.write(self.style.WARNING(
                "SIMULACIÓN: no se modificó la base. Use --aplicar después de revisar."
            ))
            return

        creados = 0
        for cliente, proxima in propuestas:
            _, created = LavadoTanque.objects.get_or_create(
                cliente=cliente,
                fecha_programada=proxima,
            )
            creados += int(created)
        self.stdout.write(self.style.SUCCESS(
            f"PROGRAMACIÓN COMPLETADA. Registros creados: {creados}"
        ))
