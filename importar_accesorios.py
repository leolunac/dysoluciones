import os
import django
import openpyxl

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "sistema7x24.settings",
)

django.setup()

from operacion.models import Accesorio


ARCHIVO = "Lista_Items.xlsx"

wb = openpyxl.load_workbook(
    ARCHIVO,
    data_only=True,
)

ws = wb.active

creados = 0
actualizados = 0
omitidos = 0

for fila in ws.iter_rows(min_row=2, values_only=True):

    codigo = fila[0]
    descripcion = fila[1]

    if not codigo or not descripcion:
        omitidos += 1
        continue

    codigo = str(codigo).strip()
    descripcion = str(descripcion).strip()

    accesorio, creado = Accesorio.objects.update_or_create(
        codigo=codigo,
        defaults={
            "descripcion": descripcion,
            "activo": True,
        },
    )

    if creado:
        creados += 1
    else:
        actualizados += 1


print("===================================")
print("IMPORTACIÓN FINALIZADA")
print("===================================")
print("Accesorios creados:", creados)
print("Accesorios actualizados:", actualizados)
print("Filas omitidas:", omitidos)
print("Total catálogo:", Accesorio.objects.count())
print("===================================")