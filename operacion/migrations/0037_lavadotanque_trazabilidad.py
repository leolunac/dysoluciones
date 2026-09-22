from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("operacion", "0036_remisiones_catalogo_y_consumo"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="lavadotanque",
            name="actividad",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="programacion_lavado",
                to="operacion.actividadtecnico",
            ),
        ),
        migrations.AddField(
            model_name="lavadotanque",
            name="actualizado_en",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddField(
            model_name="lavadotanque",
            name="creado_por",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="lavados_programados",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="lavadotanque",
            name="servicio",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="programacion_lavado",
                to="operacion.emergencia",
            ),
        ),
    ]
