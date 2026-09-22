import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("gestion_comercial", "0012_alter_cotizacion_estado"),
        ("operacion", "0036_remisiones_catalogo_y_consumo"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RevisionMaterialUtilizado",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("estado", models.CharField(choices=[("PENDIENTE", "Pendiente de revisión"), ("FACTURAR", "Facturar"), ("INCLUIDO_CONTRATO", "Incluido en contrato"), ("GARANTIA", "Garantía"), ("CORTESIA", "Cortesía"), ("NO_FACTURABLE", "No facturable")], db_index=True, default="PENDIENTE", max_length=25)),
                ("codigo_snapshot", models.CharField(blank=True, max_length=50)),
                ("descripcion_snapshot", models.CharField(max_length=250)),
                ("cantidad_snapshot", models.DecimalField(decimal_places=2, max_digits=10)),
                ("valor_unitario_sugerido", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("observaciones", models.TextField(blank=True)),
                ("revisado_en", models.DateTimeField(blank=True, null=True)),
                ("creado", models.DateTimeField(auto_now_add=True)),
                ("actualizado", models.DateTimeField(auto_now=True)),
                ("catalogo_precio", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="revisiones_materiales", to="gestion_comercial.catalogoprecio")),
                ("consumo", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="revision_facturacion", to="operacion.accesorioactividad")),
                ("revisado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="materiales_comerciales_revisados", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Revisión comercial de material utilizado",
                "verbose_name_plural": "Revisiones comerciales de materiales utilizados",
                "ordering": ["-consumo__actividad__fecha", "-consumo_id"],
            },
        ),
    ]
