from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("operacion", "0040_cliente_lavado_opcional")]
    operations = [migrations.AddField(
        model_name="emergencia", name="es_prueba",
        field=models.BooleanField(default=False, editable=False,
            help_text="Registro de prueba excluido de los indicadores de servicios del panel gerencial."),
    )]
