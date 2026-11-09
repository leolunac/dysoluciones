from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from operacion.models import Tecnico

from .forms import ConsumoInventarioForm
from .integracion_operacion import obtener_ubicacion_tecnico
from .models import ConsumoInventario, ExistenciaInventario, MovimientoInventario, UbicacionInventario
from .servicios import confirmar_consumo, fijar_saldo_inicial
from .tests import InventarioBaseTest


class ConsumoBodegaTecnicosTest(InventarioBaseTest):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.usuario)
        self.andy = self.crear_tecnico("Andy de prueba")
        self.otro = self.crear_tecnico("Segundo técnico")
        self.inactivo = self.crear_tecnico("Técnico inactivo", activo=False)
        self.ubicacion_tecnico = obtener_ubicacion_tecnico(self.andy)

    def crear_tecnico(self, nombre, activo=True):
        return Tecnico.objects.create(
            nombre=nombre, telefono="123", especialidad="Bombas",
            valor_hora_diurna=Decimal("10000"),
            valor_hora_nocturna=Decimal("15000"), activo=activo,
        )

    def datos(self, tecnicos=(), origen=None, accion="borrador"):
        return {
            "cliente": self.cliente.pk,
            "ubicacion_origen": origen if origen is not None else self.bodega.pk,
            "fecha": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
            "tecnicos": [str(t.pk) for t in tecnicos],
            "observaciones": "CONSUMO de prueba",
            "accion": accion,
            "detalles-TOTAL_FORMS": "1", "detalles-INITIAL_FORMS": "0",
            "detalles-MIN_NUM_FORMS": "0", "detalles-MAX_NUM_FORMS": "1000",
            "detalles-0-producto": self.producto.pk,
            "detalles-0-cantidad": "2.00",
        }

    def test_selector_solo_bodegas_activas_y_principal_preseleccionada(self):
        inactiva = UbicacionInventario.objects.create(
            nombre="Bodega cerrada", tipo="BODEGA", activa=False,
        )
        otra = UbicacionInventario.objects.create(
            nombre="Bodega secundaria", tipo="BODEGA", activa=True,
        )
        respuesta = self.client.get(reverse("inventario:nuevo_consumo"))
        form = respuesta.context["form"]
        self.assertQuerySetEqual(
            form.fields["ubicacion_origen"].queryset,
            [self.bodega, otra], transform=lambda obj: obj,
        )
        self.assertEqual(form.initial["ubicacion_origen"], self.bodega.pk)
        self.assertNotIn(inactiva, form.fields["ubicacion_origen"].queryset)
        self.assertNotIn(self.inactivo, form.fields["tecnicos"].queryset)
        self.assertContains(respuesta, 'name="tecnicos"')
        self.assertContains(respuesta, 'type="checkbox"')

    def test_post_rechaza_origen_tecnico_aunque_se_envie_manualmente(self):
        respuesta = self.client.post(
            reverse("inventario:nuevo_consumo"),
            self.datos([self.andy], origen=self.ubicacion_tecnico.pk),
        )
        self.assertIn("ubicacion_origen", respuesta.context["form"].errors)
        self.assertFalse(ConsumoInventario.objects.exists())
        self.assertFalse(MovimientoInventario.objects.filter(tipo="CONSUMO").exists())

    def test_post_rechaza_bodega_inactiva_y_tecnico_inactivo(self):
        cerrada = UbicacionInventario.objects.create(
            nombre="Cerrada", tipo="BODEGA", activa=False,
        )
        form = ConsumoInventarioForm(self.datos([self.inactivo], origen=cerrada.pk))
        self.assertFalse(form.is_valid())
        self.assertIn("ubicacion_origen", form.errors)
        self.assertIn("tecnicos", form.errors)

    def test_guarda_un_tecnico_y_conserva_observaciones(self):
        respuesta = self.client.post(reverse("inventario:nuevo_consumo"), self.datos([self.andy]))
        self.assertEqual(respuesta.status_code, 302)
        consumo = ConsumoInventario.objects.get()
        self.assertEqual(list(consumo.tecnicos.all()), [self.andy])
        self.assertEqual(consumo.observaciones, "CONSUMO de prueba")
        self.assertEqual(consumo.estado, "BORRADOR")
        self.assertFalse(MovimientoInventario.objects.filter(tipo="CONSUMO").exists())

    def test_varios_tecnicos_descontando_material_una_sola_vez(self):
        fijar_saldo_inicial(
            producto=self.producto, cantidad=Decimal("5"),
            precio_referencia=Decimal("10000"), unidad_medida="UNID",
            usuario=self.usuario, origen="prueba-consumo-tecnicos",
        )
        respuesta = self.client.post(
            reverse("inventario:nuevo_consumo"),
            self.datos([self.andy, self.otro], accion="confirmar_terminar"),
        )
        self.assertEqual(respuesta.status_code, 302)
        consumo = ConsumoInventario.objects.get()
        self.assertEqual(set(consumo.tecnicos.all()), {self.andy, self.otro})
        self.assertEqual(consumo.estado, "CONFIRMADO")
        confirmar_consumo(consumo.pk, self.usuario)
        movimientos = MovimientoInventario.objects.filter(tipo="CONSUMO")
        self.assertEqual(movimientos.count(), 1)
        self.assertEqual(movimientos.get().cantidad, Decimal("2"))
        saldo = ExistenciaInventario.objects.get(producto=self.producto, ubicacion=self.bodega)
        self.assertEqual(saldo.cantidad, Decimal("3"))

    def test_fallo_por_stock_revierte_consumo_y_participantes(self):
        respuesta = self.client.post(
            reverse("inventario:nuevo_consumo"),
            self.datos([self.andy, self.otro], accion="confirmar_terminar"),
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.context["form"].non_field_errors())
        self.assertFalse(ConsumoInventario.objects.exists())
        self.assertFalse(ConsumoInventario.tecnicos.through.objects.exists())
        self.assertFalse(MovimientoInventario.objects.filter(tipo="CONSUMO").exists())

    def test_consumo_sin_tecnicos_sigue_siendo_valido(self):
        respuesta = self.client.post(reverse("inventario:nuevo_consumo"), self.datos())
        self.assertEqual(respuesta.status_code, 302)
        self.assertFalse(ConsumoInventario.objects.get().tecnicos.exists())
