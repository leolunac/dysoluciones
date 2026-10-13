import re

import django.utils.timezone
from django.db import migrations, models


PATRON_CONSUMO = re.compile(r"^Consumo #(\d+)$")


def completar_fechas_operacion(apps, schema_editor):
    Movimiento = apps.get_model("inventario", "MovimientoInventario")
    Consumo = apps.get_model("inventario", "ConsumoInventario")

    consumos = dict(Consumo.objects.values_list("id", "fecha"))
    for movimiento in Movimiento.objects.all().iterator():
        fecha = movimiento.creado
        coincidencia = PATRON_CONSUMO.match(movimiento.referencia or "")
        if coincidencia:
            fecha = consumos.get(int(coincidencia.group(1)), fecha)
        movimiento.fecha_operacion = fecha
        movimiento.save(update_fields=["fecha_operacion"])


class Migration(migrations.Migration):

    dependencies = [
        ("inventario", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="movimientoinventario",
            name="fecha_operacion",
            field=models.DateTimeField(null=True, db_index=True),
        ),
        migrations.RunPython(
            completar_fechas_operacion,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="movimientoinventario",
            name="fecha_operacion",
            field=models.DateTimeField(
                default=django.utils.timezone.now,
                db_index=True,
            ),
        ),
        migrations.AlterModelOptions(
            name="movimientoinventario",
            options={"ordering": ["-fecha_operacion", "-id"]},
        ),
    ]
