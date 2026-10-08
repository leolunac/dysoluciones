from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("operacion", "0038_actividadtecnico_solicitud_sincronizacion"),
    ]

    operations = [
        migrations.CreateModel(
            name="SolicitudSincronizacionPreventivo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("solicitud", models.UUIDField(editable=False, unique=True)),
                ("accion", models.CharField(max_length=40)),
                ("respuesta", models.JSONField(default=dict)),
                ("creado", models.DateTimeField(auto_now_add=True)),
                ("preventivo", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="solicitudes_sincronizacion", to="operacion.mantenimientopreventivo")),
            ],
            options={
                "verbose_name": "Solicitud de sincronización preventiva",
                "verbose_name_plural": "Solicitudes de sincronización preventiva",
                "ordering": ["creado", "id"],
            },
        ),
    ]
