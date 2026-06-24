import csv
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sistema7x24.settings")
django.setup()

from operacion.models import Cliente

with open('clientes.csv', newline='', encoding='utf-8') as archivo:
    reader = csv.DictReader(archivo)

    for fila in reader:
        Cliente.objects.get_or_create(
            nombre=fila['cliente'],
            defaults={
                'direccion': fila['direccion'] if fila['direccion'] else 'Pendiente',
                'telefono_porteria': str(fila['telefono']) if fila['telefono'] else '000',
                'administrador': 'Pendiente',
                'email': fila['correo_electronico'] if fila['correo_electronico'] else 'pendiente@correo.com',
                'tipo_contrato': 'SIN_CONTRATO',
                'frecuencia_lavado': 6,
            }
        )

print("Clientes importados correctamente.")