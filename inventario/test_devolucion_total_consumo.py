from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from operacion.models import Accesorio, Cliente
from .correcciones import corregir_cantidad
from .models import ConsumoInventario, CorreccionCantidadConsumo, DetalleConsumoInventario, ExistenciaInventario, MovimientoInventario, ProductoInventario
from .servicios import confirmar_consumo, fijar_saldo_inicial, obtener_bodega_principal


class DevolucionTotalConsumoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = User.objects.create_user('devolucion_gestor')
        cls.usuario.groups.add(Group.objects.create(name='GESTION_INVENTARIO'))
        cls.cliente = Cliente.objects.create(nombre='UNIDAD DEVOLUCION', activo=True)
        cls.bodega = obtener_bodega_principal()
        accesorio = Accesorio.objects.create(codigo='ZD001', descripcion='UNION 2"', activo=True)
        cls.producto = ProductoInventario.objects.create(accesorio=accesorio, precio_referencia=100)
        fijar_saldo_inicial(producto=cls.producto, cantidad=20, precio_referencia=100,
                           unidad_medida='UNID', usuario=cls.usuario, origen='devolucion_test')
        cls.consumo = ConsumoInventario.objects.create(cliente=cls.cliente, ubicacion_origen=cls.bodega, creado_por=cls.usuario)
        cls.detalle = DetalleConsumoInventario.objects.create(consumo=cls.consumo, producto=cls.producto, cantidad=4)

    def setUp(self):
        self.client.force_login(self.usuario)
        self.url = reverse('inventario:corregir_cantidad_consumo', args=[self.consumo.pk, self.detalle.pk])
        self.ficha = reverse('inventario:detalle_consumo', args=[self.consumo.pk])

    def corregir(self, cantidad, revision=0):
        return corregir_cantidad(consumo_id=self.consumo.pk, detalle_id=self.detalle.pk, cantidad=cantidad,
                                 motivo='Se devolvió material no utilizado', revision=revision, usuario=self.usuario)

    def saldo(self):
        return ExistenciaInventario.objects.get(producto=self.producto, ubicacion=self.bodega).cantidad

    def libro(self, **filtros):
        r = self.client.get(reverse('inventario:exportar_consumos'), filtros)
        self.assertEqual(r.status_code, 200)
        return load_workbook(BytesIO(r.content), data_only=True)

    def test_devolucion_total_cuatro_a_cero_reintegra_cuatro(self):
        confirmar_consumo(self.consumo.pk, self.usuario)
        self.assertEqual(self.saldo(), Decimal('16'))
        cambio = self.corregir('0')
        self.detalle.refresh_from_db();self.detalle.full_clean()
        self.assertEqual(self.detalle.cantidad, Decimal('0'))
        self.assertEqual(self.saldo(), Decimal('20'))
        self.assertEqual((cambio.cantidad_anterior, cambio.cantidad_nueva), (Decimal('4'), Decimal('0')))
        self.assertEqual(cambio.movimiento.tipo, 'CORR_CONSUMO_ENTRADA')
        self.assertEqual(cambio.movimiento.cantidad, Decimal('4'))
        self.assertEqual(cambio.movimiento.destino, self.bodega)
        self.assertEqual(MovimientoInventario.objects.get(clave_idempotencia=f'CONSUMO:{self.consumo.pk}:{self.detalle.pk}').cantidad, Decimal('4'))

    def test_formulario_confirmado_acepta_cero_y_muestra_historial(self):
        confirmar_consumo(self.consumo.pk, self.usuario)
        r = self.client.get(self.url)
        self.assertEqual(r.context['form'].fields['cantidad'].min_value, Decimal('0'))
        r = self.client.post(self.url, {'cantidad': '0', 'motivo': 'No se utilizó ninguna unión', 'revision': '0'}, follow=True)
        self.assertRedirects(r, self.ficha)
        self.assertContains(r, 'Devolución total registrada')
        self.assertContains(r, 'Devuelto totalmente')
        self.assertContains(r, 'No se utilizó ninguna unión')
        self.assertEqual(self.saldo(), Decimal('20'))

    def test_borrador_sigue_exigiendo_positivo(self):
        r = self.client.get(self.url)
        self.assertEqual(r.context['form'].fields['cantidad'].min_value, Decimal('0.01'))
        r = self.client.post(self.url, {'cantidad': '0', 'motivo': 'No se utilizó ninguna unión', 'revision': '0'})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.context['form'].errors)
        with self.assertRaisesMessage(ValidationError, 'confirmados'):
            self.corregir('0')
        self.assertFalse(CorreccionCantidadConsumo.objects.exists())
        self.assertEqual(self.saldo(), Decimal('20'))

    def test_modelo_cero_solo_en_confirmado(self):
        self.detalle.cantidad = Decimal('0')
        with self.assertRaises(ValidationError):
            self.detalle.full_clean()
        confirmar_consumo(self.consumo.pk, self.usuario)
        self.corregir('0')
        self.detalle.refresh_from_db();self.detalle.full_clean()
        self.detalle.cantidad = Decimal('-1')
        with self.assertRaises(ValidationError):
            self.detalle.full_clean()

    def test_cero_a_positivo_reanuda_salida_y_audita_anterior_cero(self):
        confirmar_consumo(self.consumo.pk, self.usuario)
        primera = self.corregir('0')
        segunda = self.corregir('2', revision=primera.pk)
        self.assertEqual(segunda.cantidad_anterior, Decimal('0'))
        self.assertEqual(segunda.movimiento.tipo, 'CORR_CONSUMO_SALIDA')
        self.assertEqual(self.saldo(), Decimal('18'))
        self.assertEqual(self.libro()['Consumos']['E2'].value, 2)

    def test_reintentar_devolucion_total_no_duplica_stock(self):
        confirmar_consumo(self.consumo.pk, self.usuario)
        primera = self.corregir('0')
        with self.assertRaises(ValidationError):
            self.corregir('0')
        with self.assertRaisesMessage(ValidationError, 'diferente'):
            self.corregir('0', revision=primera.pk)
        self.assertEqual(self.saldo(), Decimal('20'))
        self.assertEqual(CorreccionCantidadConsumo.objects.count(), 1)

    def test_reactivar_sin_stock_revierte_todo(self):
        confirmar_consumo(self.consumo.pk, self.usuario)
        primera = self.corregir('0')
        otro = ConsumoInventario.objects.create(cliente=self.cliente, ubicacion_origen=self.bodega, creado_por=self.usuario)
        DetalleConsumoInventario.objects.create(consumo=otro, producto=self.producto, cantidad=20)
        confirmar_consumo(otro.pk, self.usuario)
        with self.assertRaisesMessage(ValidationError, 'Stock insuficiente'):
            self.corregir('2', revision=primera.pk)
        self.detalle.refresh_from_db()
        self.assertEqual(self.detalle.cantidad, Decimal('0'))
        self.assertEqual(self.saldo(), Decimal('0'))
        self.assertEqual(CorreccionCantidadConsumo.objects.count(), 1)

    def test_excel_devolucion_total_muestra_cero_y_auditoria(self):
        confirmar_consumo(self.consumo.pk, self.usuario)
        self.corregir('0')
        libro = self.libro()
        self.assertEqual(libro.sheetnames, ['Consumos', 'Movimientos'])
        hoja, movimientos = libro['Consumos'], libro['Movimientos']
        self.assertEqual(hoja.max_row, 3)
        self.assertEqual(hoja['C2'].value, 'ZD001')
        self.assertEqual(hoja['E2'].value, 0)
        self.assertEqual(hoja['G2'].value, 0)
        self.assertEqual(hoja['G3'].value, 0)
        self.assertEqual(movimientos['E2'].value, 4)
        self.assertEqual(movimientos['E3'].value, -4)
        self.assertEqual(movimientos['G4'].value, 0)
        self.assertIn('material no utilizado', movimientos['K3'].value)

    def test_excel_parcial_muestra_una_sola_cantidad_final(self):
        confirmar_consumo(self.consumo.pk, self.usuario)
        self.corregir('2')
        hoja = self.libro()['Consumos']
        self.assertEqual(hoja.max_row, 3)
        self.assertEqual(hoja['E2'].value, 2)
        self.assertEqual(hoja['G2'].value, 200)
        self.assertEqual(hoja['G3'].value, 200)

    def test_excel_sucesivas_correcciones_no_duplica_lineas(self):
        confirmar_consumo(self.consumo.pk, self.usuario)
        c = self.corregir('2')
        c = self.corregir('0', revision=c.pk)
        self.corregir('3', revision=c.pk)
        libro = self.libro()
        self.assertEqual(libro['Consumos'].max_row, 3)
        self.assertEqual(libro['Consumos']['E2'].value, 3)
        self.assertEqual(libro['Consumos']['G3'].value, 300)
        self.assertEqual(libro['Movimientos']['G6'].value, 300)
        self.assertEqual(self.saldo(), Decimal('17'))

    def test_excel_dos_consumos_del_mismo_producto_no_se_mezclan(self):
        confirmar_consumo(self.consumo.pk, self.usuario)
        otro = ConsumoInventario.objects.create(cliente=self.cliente, ubicacion_origen=self.bodega, creado_por=self.usuario)
        DetalleConsumoInventario.objects.create(consumo=otro, producto=self.producto, cantidad=3)
        confirmar_consumo(otro.pk, self.usuario)
        self.corregir('0')
        hoja = self.libro()['Consumos']
        self.assertEqual(hoja.max_row, 4)
        self.assertEqual([hoja['E2'].value, hoja['E3'].value], [0, 3])
        self.assertEqual(hoja['G4'].value, 300)

    def test_excel_dos_lineas_del_mismo_producto_no_se_mezclan(self):
        DetalleConsumoInventario.objects.create(consumo=self.consumo, producto=self.producto, cantidad=3)
        confirmar_consumo(self.consumo.pk, self.usuario)
        self.corregir('0')
        hoja = self.libro()['Consumos']
        self.assertEqual([hoja['E2'].value, hoja['E3'].value], [0, 3])
        self.assertEqual(hoja['G4'].value, 300)

    def test_fecha_historica_y_precio_original_se_conservan(self):
        antigua = timezone.now() - timedelta(days=60)
        ConsumoInventario.objects.filter(pk=self.consumo.pk).update(fecha=antigua)
        confirmar_consumo(self.consumo.pk, self.usuario)
        ProductoInventario.objects.filter(pk=self.producto.pk).update(precio_referencia=999)
        self.corregir('2')
        dia = timezone.localtime(antigua).date().isoformat()
        libro = self.libro(fecha_desde=dia, fecha_hasta=dia)
        self.assertEqual(libro['Consumos']['F2'].value, 100)
        self.assertEqual(libro['Consumos']['G3'].value, 200)
        self.assertEqual(libro['Movimientos']['G4'].value, 200)
        hoy = timezone.localdate().isoformat()
        self.assertEqual(self.libro(fecha_desde=hoy)['Consumos'].max_row, 2)

    def test_consumos_antiguos_y_de_actividades_se_conservan(self):
        MovimientoInventario.objects.create(producto=self.producto, tipo='CONSUMO', cantidad=2, origen=self.bodega,
                                           cliente=self.cliente, precio_referencia_snapshot=150,
                                           clave_idempotencia='ACTIVIDAD_CONSUMO:123')
        hoja = self.libro()['Consumos']
        self.assertEqual(hoja['E2'].value, 2)
        self.assertEqual(hoja['G3'].value, 300)

    def test_clave_no_puede_asociar_otro_cliente_o_producto(self):
        confirmar_consumo(self.consumo.pk, self.usuario)
        self.corregir('0')
        otro_cliente = Cliente.objects.create(nombre='Otra unidad', activo=True)
        MovimientoInventario.objects.filter(tipo='CONSUMO').update(cliente=otro_cliente)
        hoja = self.libro()['Consumos']
        # Datos incoherentes se conservan como movimientos, sin sustituir por otro consumo.
        self.assertEqual(hoja['E2'].value, 4)
        self.assertEqual(hoja['E3'].value, -4)

    def test_ajuste_sin_original_verificable_no_se_omite(self):
        MovimientoInventario.objects.create(producto=self.producto, tipo='CORR_CONSUMO_ENTRADA', cantidad=1,
                                           destino=self.bodega, cliente=self.cliente, precio_referencia_snapshot=100)
        hoja = self.libro()['Consumos']
        self.assertEqual(hoja['E2'].value, -1)
        self.assertEqual(hoja['G3'].value, -100)

    def test_sin_consumos_excel_tiene_encabezado_y_total_cero(self):
        libro = self.libro()
        for nombre in ('Consumos', 'Movimientos'):
            self.assertEqual(libro[nombre].max_row, 2)
            self.assertEqual(libro[nombre]['G2'].value, 0)

    def test_borrador_no_aparece_en_excel(self):
        self.assertEqual(self.libro()['Consumos'].max_row, 2)

    def test_estadisticas_no_muestran_consumo_devuelto_totalmente(self):
        confirmar_consumo(self.consumo.pk, self.usuario)
        self.corregir('0')
        r = self.client.get(reverse('inventario:tablero'))
        self.assertEqual(list(r.context['productos_mas_usados']), [])
        self.assertEqual(list(r.context['clientes_mayor_consumo']), [])

    def test_fechas_invalidas_devuelven_error_controlado(self):
        for datos in ({'fecha_desde': 'ayer'}, {'fecha_hasta': '2026-99-99'}, {'fecha_desde': '2026-11-30', 'fecha_hasta': '2026-11-01'}):
            self.assertEqual(self.client.get(reverse('inventario:exportar_consumos'), datos).status_code, 400)

    def test_texto_excel_no_se_interpreta_como_formula(self):
        confirmar_consumo(self.consumo.pk, self.usuario)
        Cliente.objects.filter(pk=self.cliente.pk).update(nombre='=1+1')
        r = self.client.get(reverse('inventario:exportar_consumos'))
        libro = load_workbook(BytesIO(r.content), data_only=False)
        for nombre in libro.sheetnames:
            self.assertEqual(libro[nombre]['B2'].value, '=1+1')
            self.assertEqual(libro[nombre]['B2'].data_type, 's')

    def test_restricciones_historial_aceptan_cero_rechazan_negativos(self):
        confirmar_consumo(self.consumo.pk, self.usuario)
        cambio = self.corregir('0')
        with self.assertRaises(IntegrityError), transaction.atomic():
            CorreccionCantidadConsumo.objects.filter(pk=cambio.pk).update(cantidad_nueva=-1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CorreccionCantidadConsumo.objects.filter(pk=cambio.pk).update(cantidad_anterior=-1)

    def test_fallo_de_movimiento_devolucion_total_revierte_cantidad(self):
        confirmar_consumo(self.consumo.pk, self.usuario)
        with patch('inventario.correcciones.registrar_movimiento', side_effect=ValidationError('Fallo simulado')):
            with self.assertRaises(ValidationError):
                self.corregir('0')
        self.detalle.refresh_from_db()
        self.assertEqual(self.detalle.cantidad, Decimal('4'))
        self.assertEqual(self.saldo(), Decimal('16'))
        self.assertFalse(CorreccionCantidadConsumo.objects.exists())
