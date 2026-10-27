import django.db.models.deletion
import gestion_humana.models
import gestion_humana.storage
from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('gestion_humana', '0002_empleado_tipo_empleado'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(
        name='DesprendiblePago',
        fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('periodo_inicio', models.DateField()), ('periodo_fin', models.DateField()),
            ('archivo', models.FileField(storage=gestion_humana.storage.almacenamiento_privado, upload_to=gestion_humana.models.ruta_privada, validators=[FileExtensionValidator(['pdf']), gestion_humana.models.validar_tamano_archivo])),
            ('creado', models.DateTimeField(auto_now_add=True)),
            ('creado_por', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ('empleado', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='desprendibles', to='gestion_humana.empleado')),
        ], options={'ordering': ['-periodo_fin', '-pk'], 'constraints': [models.UniqueConstraint(fields=('empleado', 'periodo_inicio', 'periodo_fin'), name='desprendible_empleado_periodo_unico')]},
    )]
