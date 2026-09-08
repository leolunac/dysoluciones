import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def preparar_registros_anteriores(apps, schema_editor):
    Mantenimiento = apps.get_model("operacion", "MantenimientoPreventivo")
    Actividad = apps.get_model("operacion", "ActividadTecnico")

    for preventivo in Mantenimiento.objects.select_related("actividad").iterator():
        cambios = []
        if preventivo.codigo_verificacion is None:
            preventivo.codigo_verificacion = uuid.uuid4()
            cambios.append("codigo_verificacion")

        actividad = preventivo.actividad
        if hasattr(actividad, "programacion_preventiva"):
            preventivo.estado_revision = "LEGADO"
            cambios.append("estado_revision")

        if cambios:
            preventivo.save(update_fields=cambios)

    # Los correctivos históricos no reciben una hora de envío inventada.
    Actividad.objects.filter(numero_informe="").update(numero_informe=None)


class Migration(migrations.Migration):

    dependencies = [
        ("operacion", "0033_origen_nota_keep"),
        ("portal_cliente", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="actividadtecnico",
            name="enviado_en",
            field=models.DateTimeField(
                blank=True,
                help_text="Fecha y hora del servidor en que el técnico envió el informe.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="actividadtecnico",
            name="numero_informe",
            field=models.CharField(
                blank=True,
                help_text="Consecutivo asignado cuando el técnico envía el informe.",
                max_length=30,
                null=True,
                unique=True,
            ),
        ),
        migrations.AddField(
            model_name="programacionmantenimientopreventivo",
            name="sector",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="preventivos_programados",
                to="operacion.sectorcliente",
            ),
        ),
        migrations.AlterField(
            model_name="programacionmantenimientopreventivo",
            name="estado",
            field=models.CharField(
                choices=[
                    ("PROGRAMADO", "Programado"),
                    ("EN_PROCESO", "En proceso"),
                    ("PENDIENTE_REVISION", "Pendiente de revisión"),
                    ("DEVUELTO", "Devuelto para corregir"),
                    ("PUBLICADO", "Aprobado y publicado"),
                    ("EJECUTADO", "Ejecutado antes del nuevo flujo"),
                    ("REPROGRAMADO", "Reprogramado"),
                    ("CANCELADO", "Cancelado"),
                ],
                default="PROGRAMADO",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="mantenimientopreventivo",
            name="cliente_informado",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="mantenimientopreventivo",
            name="codigo_verificacion",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="mantenimientopreventivo",
            name="documento_cliente",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="mantenimiento_preventivo",
                to="portal_cliente.documentocliente",
            ),
        ),
        migrations.AddField(
            model_name="mantenimientopreventivo",
            name="estado_anomalia",
            field=models.CharField(
                choices=[
                    ("NO_APLICA", "Sin anomalías"),
                    ("PENDIENTE_RESPUESTA", "Pendiente de respuesta del cliente"),
                    ("PENDIENTE_COTIZACION", "Pendiente de cotización"),
                    ("INCLUIDO_PRESUPUESTO", "Incluido en presupuesto del cliente"),
                    ("APROBADA", "Corrección aprobada"),
                    ("APLAZADA", "Corrección aplazada"),
                    ("NO_APROBADA", "Corrección no aprobada"),
                    ("CORRECTIVO_CREADO", "Servicio correctivo creado"),
                    ("CERRADA", "Anomalía cerrada"),
                ],
                default="NO_APLICA",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="mantenimientopreventivo",
            name="estado_revision",
            field=models.CharField(
                choices=[
                    ("BORRADOR", "Borrador del técnico"),
                    ("PENDIENTE", "Pendiente de revisión"),
                    ("DEVUELTO", "Devuelto para corregir"),
                    ("PUBLICADO", "Aprobado y publicado"),
                    ("LEGADO", "Ejecutado antes del nuevo flujo"),
                ],
                default="BORRADOR",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="mantenimientopreventivo",
            name="fecha_cliente_informado",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="mantenimientopreventivo",
            name="medio_notificacion",
            field=models.CharField(
                blank=True,
                help_text="Ejemplo: llamada, correo electrónico o reunión.",
                max_length=120,
            ),
        ),
        migrations.AddField(
            model_name="mantenimientopreventivo",
            name="observaciones_revision",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="mantenimientopreventivo",
            name="resultado_preventivo",
            field=models.CharField(
                blank=True,
                choices=[
                    ("SIN_NOVEDAD", "Mantenimiento realizado sin anomalías"),
                    ("CON_NOVEDAD", "Mantenimiento realizado con anomalías"),
                ],
                max_length=20,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="mantenimientopreventivo",
            name="revisado_en",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="mantenimientopreventivo",
            name="revisado_por",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="preventivos_revisados",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.CreateModel(
            name="SeguimientoAnomaliaPreventivo",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("estado_anterior", models.CharField(blank=True, max_length=30)),
                (
                    "estado_nuevo",
                    models.CharField(
                        choices=[
                            ("NO_APLICA", "Sin anomalías"),
                            ("PENDIENTE_RESPUESTA", "Pendiente de respuesta del cliente"),
                            ("PENDIENTE_COTIZACION", "Pendiente de cotización"),
                            ("INCLUIDO_PRESUPUESTO", "Incluido en presupuesto del cliente"),
                            ("APROBADA", "Corrección aprobada"),
                            ("APLAZADA", "Corrección aplazada"),
                            ("NO_APROBADA", "Corrección no aprobada"),
                            ("CORRECTIVO_CREADO", "Servicio correctivo creado"),
                            ("CERRADA", "Anomalía cerrada"),
                        ],
                        max_length=30,
                    ),
                ),
                ("observacion", models.TextField(blank=True)),
                ("creado", models.DateTimeField(auto_now_add=True)),
                (
                    "preventivo",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="seguimientos_anomalia",
                        to="operacion.mantenimientopreventivo",
                    ),
                ),
                (
                    "usuario",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="seguimientos_anomalias_preventivas",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Seguimiento de anomalía preventiva",
                "verbose_name_plural": "Seguimientos de anomalías preventivas",
                "ordering": ["-creado", "-id"],
            },
        ),
        migrations.RunPython(
            preparar_registros_anteriores,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="mantenimientopreventivo",
            name="codigo_verificacion",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
