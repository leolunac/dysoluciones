from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("operacion", "0039_solicitudsincronizacionpreventivo")]

    operations = [
        migrations.AlterField(
            model_name="cliente",
            name="frecuencia_lavado",
            field=models.IntegerField(
                choices=[(None, "Sin lavado periódico"), (4, "Cada 4 meses"), (6, "Cada 6 meses")],
                null=True, blank=True, default=None,
                help_text="Seleccione 4 o 6 meses solo si la unidad tiene lavado periódico. "
                          "Sin lavado periódico permite registrar servicios ocasionales.",
            ),
        ),
    ]
