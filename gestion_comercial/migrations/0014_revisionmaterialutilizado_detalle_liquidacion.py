from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("gestion_comercial", "0013_revisionmaterialutilizado"),
    ]

    operations = [
        migrations.AddField(
            model_name="revisionmaterialutilizado",
            name="detalle_liquidacion",
            field=models.OneToOneField(
                blank=True,
                help_text=(
                    "Detalle de liquidación creado a partir de este consumo. "
                    "Impide incluir el mismo material más de una vez."
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="revision_material_origen",
                to="gestion_comercial.detalleliquidacion",
            ),
        ),
    ]
