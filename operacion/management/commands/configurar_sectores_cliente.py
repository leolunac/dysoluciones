"""Prepara Oficinas/Viviendas únicamente para el cliente confirmado en desarrollo."""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from operacion.models import Cliente, SectorCliente


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument('--cliente', type=int, required=True)
        parser.add_argument('--nombre-exacto', required=True)
        parser.add_argument('--aplicar', action='store_true')
        parser.add_argument('--desarrollo', action='store_true')

    def handle(self, *args, **options):
        if options['aplicar'] and (not options['desarrollo'] or not settings.DEBUG):
            raise CommandError('Aplicación exclusiva para desarrollo: requiere --desarrollo y DEBUG=True.')
        with transaction.atomic():
            try:
                cliente = Cliente.objects.select_for_update().get(pk=options['cliente'])
            except Cliente.DoesNotExist:
                raise CommandError('No existe el cliente indicado.')
            if cliente.nombre != options['nombre_exacto']:
                raise CommandError('El nombre no coincide exactamente. No se modificó ningún dato.')
            nombres = ('Oficinas', 'Viviendas')
            existentes = list(cliente.sectores.values_list('nombre', flat=True))
            if any(n not in nombres for n in existentes):
                raise CommandError('El cliente tiene otros sectores o nombres diferentes; requiere revisión.')
            self.stdout.write(f'Cliente: {cliente.pk} — {cliente.nombre}')
            for nombre in nombres:
                self.stdout.write(('EXISTE: ' if nombre in existentes else 'NUEVO: ') + nombre)
                if options['aplicar']:
                    SectorCliente.objects.get_or_create(cliente=cliente, nombre=nombre)
        self.stdout.write('Configuración aplicada. No se asignaron sectores a registros anteriores.' if options['aplicar'] else 'Vista previa. No se modificó ningún dato.')
