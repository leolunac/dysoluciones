from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [('gestion_humana', '0003_desprendiblepago'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.AddField(model_name='desprendiblepago', name='activo', field=models.BooleanField(default=True)),
        migrations.AddField(model_name='desprendiblepago', name='retirado', field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='desprendiblepago', name='retirado_por', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='desprendibles_retirados', to=settings.AUTH_USER_MODEL)),
        migrations.RemoveConstraint(model_name='desprendiblepago', name='desprendible_empleado_periodo_unico'),
        migrations.AddConstraint(model_name='desprendiblepago', constraint=models.UniqueConstraint(fields=('empleado', 'periodo_inicio', 'periodo_fin'), condition=models.Q(activo=True), name='desprendible_empleado_periodo_unico')),
    ]
