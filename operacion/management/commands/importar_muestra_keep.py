"""Vista previa por defecto; importación explícita y confirmada solo en desarrollo."""
from pathlib import Path
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError
from operacion.importacion_keep import leer_muestra, preparar_plan, aplicar_muestra


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument('--archivo', type=Path, required=True)
        parser.add_argument('--usuario', required=True)
        parser.add_argument('--aplicar', action='store_true')
        parser.add_argument('--desarrollo', action='store_true')
        parser.add_argument('--confirmar', default='')

    def handle(self, *args, **options):
        if options['aplicar']:
            host=settings.DATABASES['default'].get('HOST','')
            if not options['desarrollo'] or not settings.DEBUG or host not in ('',None,'localhost','127.0.0.1','::1'):
                raise CommandError('Esta prueba requiere --desarrollo, DEBUG=True y una base de datos local.')
            if len(options['confirmar'])!=64:
                raise CommandError('Falta --confirmar con la huella que muestra la vista previa.')
        User=get_user_model()
        try:
            usuario=User.objects.get(**{User.USERNAME_FIELD:options['usuario']})
        except User.DoesNotExist:
            raise CommandError('No existe el usuario indicado; no se crean usuarios automáticamente.')
        try:
            registros,lote=leer_muestra(options['archivo'])
            plan,firma=preparar_plan(registros,usuario,lote)
        except OSError as exc:
            raise CommandError(f'No se pudo leer la muestra: {exc}') from exc
        except DatabaseError as exc:
            raise CommandError('No se pudo consultar el origen de las notas. Compruebe la conexión y que la migración 0033 esté aplicada.') from exc
        for item in plan:
            p=item['propuesta'];destino='Pendiente de confirmar cliente o tratamiento de proveedor'
            if item['accion']!='PENDIENTE':
                destino=f"Cliente {item['cliente'].pk}: {item['cliente'].nombre}"
                if item['sector']:destino+=f" · {item['sector'].nombre}"
            self.stdout.write(f"{item['accion']} | {p['date']} | {p['reference']} | {destino}")
        for accion in ('NUEVA','YA IMPORTADA','PENDIENTE'):
            self.stdout.write(f"{accion}: {sum(i['accion']==accion for i in plan)}")
        self.stdout.write('Estado inicial: Importado / por revisar. Sin técnico, responsable ni compromiso asignados.')
        self.stdout.write('Fecha original conservada; usuario de incorporación: '+usuario.get_username())
        self.stdout.write('HUELLA DE REVISION: '+firma)
        if not options['aplicar']:
            self.stdout.write('Vista previa completada. No se modificó ningún dato.');return
        nuevas,existentes,pendientes=aplicar_muestra(registros,usuario,lote,options['confirmar'])
        self.stdout.write(f'Importación completada: {len(nuevas)} nuevas, {existentes} ya existentes, {pendientes} pendientes sin importar.')
        self.stdout.write('IDs de nuevas novedades: '+', '.join(map(str,nuevas)))
