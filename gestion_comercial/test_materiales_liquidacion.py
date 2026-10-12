from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from operacion.models import (
    Accesorio,
    AccesorioActividad,
    ActividadTecnico,
    Cliente,
    Tecnico,
)

from .models import (
    CatalogoPrecio,
    DetalleLiquidacion,
    Liquidacion,
    RevisionMaterialUtilizado,
)


class MaterialesLiquidacionTests(TestCase):

    def setUp(self):
        self.usuario = User.objects.create_user(
            username="auxiliar_materiales",
            password="prueba-segura",
        )
        grupo = Group.objects.create(name="GESTION_AUXILIAR")
        self.usuario.groups.add(grupo)
        self.client.force_login(self.usuario)

        self.cliente = self._crear_cliente("UNIDAD PRUEBA", "900001")
        self.otro_cliente = self._crear_cliente("OTRA UNIDAD", "900002")
        self.tecnico = Tecnico.objects.create(
            nombre="Técnico Prueba",
            telefono="3000000000",
            especialidad="Bombas",
            valor_hora_diurna=Decimal("10000.00"),
            valor_hora_nocturna=Decimal("15000.00"),
        )
        self.accesorio = Accesorio.objects.create(
            codigo="A-PRUEBA",
            descripcion="Accesorio de prueba",
        )
        self.catalogo = CatalogoPrecio.objects.create(
            codigo="A-PRUEBA",
            descripcion="Accesorio de prueba",
            valor=Decimal("25000.00"),
        )
        self.liquidacion = Liquidacion.objects.create(
            cliente=self.cliente,
            descripcion="Correctivo de prueba",
            creado_por=self.usuario,
        )
        self.revision = self._crear_revision(self.cliente, "INF-PRUEBA-1")

    def _crear_cliente(self, nombre, nit):
        return Cliente.objects.create(
            nombre=nombre,
            nit=nit,
            direccion="Dirección de prueba",
            telefono_porteria="000",
            administrador="Administración",
            email=f"{nit}@example.com",
            tipo_contrato="SIN_CONTRATO",
            frecuencia_lavado=6,
        )

    def _crear_revision(self, cliente, informe):
        actividad = ActividadTecnico.objects.create(
            tecnico=self.tecnico,
            cliente=cliente,
            tipo_actividad="CORRECTIVO",
            labor_realizada="Cambio de accesorio",
            numero_informe=informe,
        )
        consumo = AccesorioActividad.objects.create(
            actividad=actividad,
            accesorio=self.accesorio,
            cantidad=Decimal("2.00"),
        )
        return RevisionMaterialUtilizado.objects.create(
            consumo=consumo,
            estado="FACTURAR",
            catalogo_precio=self.catalogo,
            codigo_snapshot=self.accesorio.codigo,
            descripcion_snapshot=self.accesorio.descripcion,
            cantidad_snapshot=Decimal("2.00"),
            valor_unitario_sugerido=Decimal("25000.00"),
            revisado_por=self.usuario,
        )

    def test_agrega_material_utilizado_una_sola_vez(self):
        url = reverse(
            "gestion_comercial:agregar_materiales_liquidacion",
            args=[self.liquidacion.pk],
        )

        respuesta = self.client.post(url, {"materiales": [self.revision.pk]})

        self.assertRedirects(
            respuesta,
            reverse(
                "gestion_comercial:editar_liquidacion",
                args=[self.liquidacion.pk],
            ),
        )
        self.revision.refresh_from_db()
        detalle = self.revision.detalle_liquidacion
        self.assertIsNotNone(detalle)
        self.assertEqual(detalle.liquidacion, self.liquidacion)
        self.assertEqual(detalle.tipo, "MATERIAL")
        self.assertEqual(detalle.cantidad, Decimal("2.00"))
        self.assertEqual(detalle.valor_unitario, Decimal("25000.00"))
        self.assertEqual(detalle.subtotal, Decimal("50000.00"))

        self.client.post(url, {"materiales": [self.revision.pk]})
        self.assertEqual(
            DetalleLiquidacion.objects.filter(
                liquidacion=self.liquidacion,
            ).count(),
            1,
        )

    def test_segundo_envio_a_revision_informa_que_ya_fue_enviada(self):
        DetalleLiquidacion.objects.create(
            liquidacion=self.liquidacion,
            tipo="MANO_OBRA",
            descripcion="Mano de obra de prueba",
            cantidad=Decimal("1.00"),
            valor_unitario=Decimal("10000.00"),
        )
        url = reverse(
            "gestion_comercial:enviar_revision",
            args=[self.liquidacion.pk],
        )

        primera_respuesta = self.client.post(url, follow=True)
        self.assertContains(
            primera_respuesta,
            "La liquidación fue enviada a revisión.",
        )
        self.liquidacion.refresh_from_db()
        self.assertEqual(self.liquidacion.estado, "REVISION")

        segunda_respuesta = self.client.post(url, follow=True)
        self.assertEqual(segunda_respuesta.status_code, 200)
        self.assertContains(
            segunda_respuesta,
            "Esta liquidación ya fue enviada a revisión.",
        )
        self.liquidacion.refresh_from_db()
        self.assertEqual(self.liquidacion.estado, "REVISION")

    def test_rechaza_material_de_otra_unidad(self):
        revision_ajena = self._crear_revision(
            self.otro_cliente,
            "INF-PRUEBA-2",
        )
        url = reverse(
            "gestion_comercial:agregar_materiales_liquidacion",
            args=[self.liquidacion.pk],
        )

        self.client.post(url, {"materiales": [revision_ajena.pk]})

        revision_ajena.refresh_from_db()
        self.assertIsNone(revision_ajena.detalle_liquidacion)
        self.assertFalse(self.liquidacion.detalles.exists())

    def test_eliminar_detalle_libera_material_para_otra_liquidacion(self):
        url_agregar = reverse(
            "gestion_comercial:agregar_materiales_liquidacion",
            args=[self.liquidacion.pk],
        )
        self.client.post(url_agregar, {"materiales": [self.revision.pk]})
        self.revision.refresh_from_db()
        detalle_id = self.revision.detalle_liquidacion_id

        self.client.post(
            reverse(
                "gestion_comercial:eliminar_detalle",
                args=[detalle_id],
            )
        )

        self.revision.refresh_from_db()
        self.assertIsNone(self.revision.detalle_liquidacion_id)

    def test_material_liquidado_no_se_reclasifica(self):
        self.usuario.groups.add(
            Group.objects.create(name="GESTION_FACTURACION")
        )
        self.client.post(
            reverse(
                "gestion_comercial:agregar_materiales_liquidacion",
                args=[self.liquidacion.pk],
            ),
            {"materiales": [self.revision.pk]},
        )

        self.client.post(
            reverse(
                "gestion_comercial:clasificar_material_utilizado",
                args=[self.revision.consumo_id],
            ),
            {"estado": "GARANTIA"},
        )

        self.revision.refresh_from_db()
        self.assertEqual(self.revision.estado, "FACTURAR")

    def test_edicion_conserva_origen_cantidad_y_tipo(self):
        self.client.post(
            reverse(
                "gestion_comercial:agregar_materiales_liquidacion",
                args=[self.liquidacion.pk],
            ),
            {"materiales": [self.revision.pk]},
        )
        self.revision.refresh_from_db()
        detalle = self.revision.detalle_liquidacion

        self.client.post(
            reverse(
                "gestion_comercial:editar_detalle",
                args=[detalle.pk],
            ),
            {
                "tipo": "OTRO",
                "descripcion": "Descripción alterada",
                "cantidad": "99",
                "valor_unitario": "27000",
                "observaciones": "Precio comercial ajustado",
            },
        )

        detalle.refresh_from_db()
        self.assertEqual(detalle.tipo, "MATERIAL")
        self.assertEqual(detalle.catalogo, self.catalogo)
        self.assertEqual(detalle.descripcion, self.revision.descripcion_snapshot)
        self.assertEqual(detalle.cantidad, self.revision.cantidad_snapshot)
        self.assertEqual(detalle.valor_unitario, Decimal("27000.00"))
