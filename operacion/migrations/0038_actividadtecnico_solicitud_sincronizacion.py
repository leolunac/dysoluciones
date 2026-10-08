from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("operacion", "0037_lavadotanque_trazabilidad"),
    ]

    operations = [
        migrations.AddField(
            model_name="actividadtecnico",
            name="solicitud_sincronizacion",
            field=models.UUIDField(
                blank=True,
                editable=False,
                help_text=(
                    "Identificador generado en el dispositivo para impedir envíos "
                    "y consumos duplicados al recuperar la conexión."
                ),
                null=True,
                unique=True,
            ),
        ),
    ]
