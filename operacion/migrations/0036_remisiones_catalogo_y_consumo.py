from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models


def relacionar_datos_existentes(apps, schema_editor):
    Accesorio = apps.get_model("operacion", "Accesorio")
    AccesorioActividad = apps.get_model("operacion", "AccesorioActividad")
    DetalleRemision = apps.get_model("operacion", "DetalleRemision")
    RemisionTecnico = apps.get_model("operacion", "RemisionTecnico")
    alias = schema_editor.connection.alias

    por_codigo = {}
    por_descripcion = {}

    for accesorio in Accesorio.objects.using(alias).all().iterator():
        codigo = (accesorio.codigo or "").strip().casefold()
        descripcion = (accesorio.descripcion or "").strip().casefold()
        if codigo:
            por_codigo.setdefault(codigo, []).append(accesorio.pk)
        if descripcion:
            por_descripcion.setdefault(descripcion, []).append(accesorio.pk)

    for detalle in DetalleRemision.objects.using(alias).filter(
        accesorio__isnull=True,
    ).iterator():
        codigo = (detalle.codigo_accesorio or "").strip().casefold()
        descripcion = (detalle.descripcion_accesorio or "").strip().casefold()
        candidatos = por_codigo.get(codigo, []) if codigo else []
        if len(candidatos) != 1 and descripcion:
            candidatos = por_descripcion.get(descripcion, [])
        if len(candidatos) == 1:
            DetalleRemision.objects.using(alias).filter(pk=detalle.pk).update(
                accesorio_id=candidatos[0],
            )

    usos = AccesorioActividad.objects.using(alias).filter(
        detalle_remision__isnull=True,
        accesorio__isnull=False,
        actividad__remision__isnull=False,
    ).values_list(
        "pk",
        "accesorio_id",
        "actividad__remision_id",
    )

    for uso_id, accesorio_id, remision_id in usos.iterator():
        coincidencias = list(
            DetalleRemision.objects.using(alias).filter(
                remision_id=remision_id,
                accesorio_id=accesorio_id,
            ).values_list("pk", flat=True)[:2]
        )
        if len(coincidencias) == 1:
            AccesorioActividad.objects.using(alias).filter(pk=uso_id).update(
                detalle_remision_id=coincidencias[0],
            )

    for detalle in DetalleRemision.objects.using(alias).filter(
        accesorio__isnull=False,
    ).iterator():
        total = AccesorioActividad.objects.using(alias).filter(
            detalle_remision_id=detalle.pk,
        ).aggregate(total=models.Sum("cantidad"))["total"] or Decimal("0.00")
        # Nunca reducimos una conciliación histórica capturada manualmente.
        # Solo elevamos el consumo si los informes técnicos demuestran una
        # cantidad superior.
        if total > detalle.cantidad_utilizada:
            DetalleRemision.objects.using(alias).filter(pk=detalle.pk).update(
                cantidad_utilizada=total,
            )

    for remision in RemisionTecnico.objects.using(alias).all().iterator():
        detalles = list(
            DetalleRemision.objects.using(alias).filter(
                remision_id=remision.pk,
            ).values_list(
                "cantidad_entregada",
                "cantidad_utilizada",
                "cantidad_devuelta",
            )
        )
        conciliada = bool(detalles) and all(
            entregada - utilizada - devuelta == Decimal("0.00")
            for entregada, utilizada, devuelta in detalles
        )
        RemisionTecnico.objects.using(alias).filter(pk=remision.pk).update(
            estado="CONCILIADA" if conciliada else "PENDIENTE",
        )


class Migration(migrations.Migration):

    dependencies = [
        ("operacion", "0035_lavado_como_actividad_tecnica"),
    ]

    operations = [
        migrations.AddField(
            model_name="detalleremision",
            name="accesorio",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Accesorio del catálogo. Los campos de código y descripción "
                    "conservan la información histórica de la remisión."
                ),
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="detalles_remision",
                to="operacion.accesorio",
            ),
        ),
        migrations.AddField(
            model_name="accesorioactividad",
            name="detalle_remision",
            field=models.ForeignKey(
                blank=True,
                help_text="Renglón de la remisión que respalda este consumo.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="usos_en_actividades",
                to="operacion.detalleremision",
            ),
        ),
        migrations.RunPython(
            relacionar_datos_existentes,
            migrations.RunPython.noop,
        ),
    ]
