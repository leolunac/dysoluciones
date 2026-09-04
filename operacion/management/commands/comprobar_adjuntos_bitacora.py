from uuid import uuid4
from django.core.management.base import BaseCommand, CommandError
from operacion.adjuntos_bitacora import almacenamiento_privado, raiz_privada, guardar_archivo_privado


class Command(BaseCommand):
    help = 'Comprueba la carpeta privada y Pillow sin modificar registros de la base de datos.'

    def handle(self, *args, **options):
        try:
            from PIL import Image
            almacen = almacenamiento_privado()
            nombre = guardar_archivo_privado(almacen, uuid4(), {'data': b'comprobacion de escritura', 'extension': '.pdf'})
            try:
                with almacen.open(nombre, 'rb') as f:
                    if f.read() != b'comprobacion de escritura':
                        raise CommandError('No se pudo verificar la lectura privada.')
            finally:
                almacen.delete(nombre)
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS('Almacenamiento privado: escritura y lectura correctas.'))
        self.stdout.write('Carpeta: ' + str(raiz_privada()))
        self.stdout.write('Pillow: ' + Image.__version__)
        self.stdout.write('Incluya esta carpeta junto con la base de datos en los respaldos. No la publique como /media/ o /static/.')
