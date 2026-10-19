from django.db import migrations, models


def clasificar_empleados_vinculados(apps, schema_editor):
    Empleado = apps.get_model("gestion_humana", "Empleado")
    Empleado.objects.filter(tecnico__isnull=False).update(tipo_empleado="TECNICO")


class Migration(migrations.Migration):
    dependencies = [
        ("gestion_humana", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="empleado",
            name="tipo_empleado",
            field=models.CharField(
                choices=[
                    ("TECNICO", "Técnico"),
                    ("ADMINISTRATIVO", "Administrativo"),
                ],
                db_index=True,
                default="ADMINISTRATIVO",
                max_length=20,
            ),
        ),
        migrations.RunPython(
            clasificar_empleados_vinculados,
            migrations.RunPython.noop,
        ),
    ]
