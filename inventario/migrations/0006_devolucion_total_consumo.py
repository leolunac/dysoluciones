from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("inventario", "0005_correccion_cantidad_entrada")]

    operations = [
        migrations.RemoveConstraint(model_name="correccioncantidadconsumo", name="inventario_corr_anterior_positiva"),
        migrations.RemoveConstraint(model_name="correccioncantidadconsumo", name="inventario_corr_nueva_positiva"),
        migrations.AddConstraint(model_name="correccioncantidadconsumo", constraint=models.CheckConstraint(condition=models.Q(cantidad_anterior__gte=0), name="inventario_corr_anterior_no_negativa")),
        migrations.AddConstraint(model_name="correccioncantidadconsumo", constraint=models.CheckConstraint(condition=models.Q(cantidad_nueva__gte=0), name="inventario_corr_nueva_no_negativa")),
    ]
