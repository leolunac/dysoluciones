from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("gestion_comercial", "0014_revisionmaterialutilizado_detalle_liquidacion")]
    operations = [migrations.AddField(
        model_name="cotizacion", name="es_prueba",
        field=models.BooleanField(default=False, editable=False,
            help_text="Cotización de prueba excluida de la gráfica del panel gerencial."),
    )]
