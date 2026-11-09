from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inventario", "0002_movimientoinventario_fecha_operacion"),
    ]

    operations = [
        migrations.AddField(
            model_name="consumoinventario",
            name="tecnicos",
            field=models.ManyToManyField(
                blank=True,
                help_text="Participantes de la labor; la cantidad consumida no se divide ni se duplica.",
                related_name="consumos_bodega_participados",
                to="operacion.tecnico",
                verbose_name="Técnicos que realizaron la labor",
            ),
        ),
    ]
