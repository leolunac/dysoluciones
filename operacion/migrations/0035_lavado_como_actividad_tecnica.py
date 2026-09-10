from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("operacion", "0034_flujo_revision_informes"),
    ]

    operations = [
        migrations.AlterField(
            model_name="emergencia",
            name="tipo_servicio",
            field=models.CharField(
                choices=[
                    ("EMERGENCIA", "Emergencia"),
                    ("CORRECTIVO", "Correctivo"),
                    ("LAVADO", "Lavado de tanques"),
                    ("GARANTIA", "Garantía"),
                    ("REVISION", "Revisión"),
                ],
                default="CORRECTIVO",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="actividadtecnico",
            name="tipo_actividad",
            field=models.CharField(
                choices=[
                    ("CORRECTIVO", "Correctivo"),
                    ("LAVADO", "Lavado de tanques"),
                    ("DIAGNOSTICO", "Visita de diagnóstico"),
                    ("REGRESO", "Regreso a unidad"),
                    ("GARANTIA", "Garantía"),
                    ("PREVENTIVO", "Mantenimiento preventivo"),
                    ("INSTALACION", "Instalación"),
                    ("OTRO", "Otro"),
                ],
                default="CORRECTIVO",
                max_length=30,
            ),
        ),
    ]
