from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models.deletion import ProtectedError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from operacion.models import Accesorio, Cliente
from .correcciones_entradas import corregir_cantidad_entrada
from .models import (
    ConsumoInventario, CorreccionCantidadEntrada, DetalleConsumoInventario,
    DetalleEntradaInventario, EntradaInventario, ExistenciaInventario,
    MovimientoInventario, ProductoInventario, Proveedor, UbicacionInventario,
)
from .servicios import confirmar_consumo, confirmar_entrada, fijar_saldo_inicial, obtener_bodega_principal


class CorreccionesEntradaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.gestor = User.objects.create_user('gestor_compras')
        cls.gestor.groups.add(Group.objects.create(name='GESTION_INVENTARIO'))
        cls.gerencia = User.objects.create_user('lector_compras')
        cls.gerencia.groups.add(Group.objects.create(name='GESTION_GERENCIA'))
        cls.externo = User.objects.create_user('externo_compras')
        cls.proveedor = Proveedor.objects.create(nombre='PROVEEDOR CORRECCIONES', nit='9019876')
        cls.cliente = Cliente.objects.create(nombre='UNIDAD COMPRA', activo=True)
        accesorio = Accesorio.objects.create(codigo='ZE01', descripcion='ACCESORIO COMPRA', activo=True)
        cls.producto = ProductoInventario.objects.create(accesorio=accesorio)
        cls.bodega = obtener_bodega_principal()
        fijar_saldo_inicial(producto=cls.producto, cantidad=20, precio_referencia=100,
                           unidad_medida='UNID', usuario=cls.gestor, origen='entrada_test')
        cls.entrada = EntradaInventario.objects.create(
            proveedor=cls.proveedor, numero_factura='FV-CORREGIR', fecha_factura=date(2026, 10, 20),
            creado_por=cls.gestor, observaciones='Conservar observaciones',
        )
        cls.detalle = DetalleEntradaInventario.objects.create(
            entrada=cls.entrada, producto=cls.producto, cantidad=10,
            precio_unitario_lista=200, porcentaje_descuento=10,
        )

    def setUp(self):
        self.client.force_login(self.gestor)
        self.lista = reverse('inventario:lista_entradas')
        self.ficha = reverse('inventario:detalle_entrada', args=[self.entrada.pk])
        self.url = reverse('inventario:corregir_cantidad_entrada', args=[self.entrada.pk, self.detalle.pk])

    def corregir(self, cantidad, revision=0, motivo='Cantidad recibida diferente', usuario=None):
        return corregir_cantidad_entrada(
            entrada_id=self.entrada.pk, detalle_id=self.detalle.pk, cantidad=cantidad,
            motivo=motivo, revision=revision, usuario=usuario or self.gestor,
        )

    def saldo(self, bodega=None):
        return ExistenciaInventario.objects.get(producto=self.producto, ubicacion=bodega or self.bodega).cantidad

    def original(self):
        return MovimientoInventario.objects.get(clave_idempotencia=f'ENTRADA:{self.entrada.pk}:{self.detalle.pk}')

    def test_borrador_corrige_y_audita_sin_mover_stock(self):
        c = self.corregir('8')
        self.detalle.refresh_from_db()
        self.assertEqual(self.detalle.cantidad, Decimal('8'))
        self.assertEqual(self.saldo(), Decimal('20'))
        self.assertIsNone(c.movimiento_id)
        self.assertEqual(c.estado_entrada, 'BORRADOR')
        self.assertEqual((c.cantidad_anterior, c.cantidad_nueva), (Decimal('10'), Decimal('8')))
        self.assertEqual(c.registrado_por, self.gestor)
        self.assertEqual(MovimientoInventario.objects.count(), 1)

    def test_confirmar_borrador_usa_cantidad_corregida(self):
        self.corregir('8')
        confirmar_entrada(self.entrada.pk, self.gestor)
        self.assertEqual(self.saldo(), Decimal('28'))
        self.assertEqual(self.original().cantidad, Decimal('8'))
        self.assertEqual(self.original().costo_neto_snapshot, Decimal('180'))

    def test_confirmada_aumentar_ingresa_solo_diferencia(self):
        confirmar_entrada(self.entrada.pk, self.gestor)
        original = self.original()
        c = self.corregir('13')
        self.assertEqual(self.saldo(), Decimal('33'))
        self.assertEqual(c.movimiento.tipo, 'CORR_ENTRADA_INGRESO')
        self.assertEqual(c.movimiento.cantidad, Decimal('3'))
        self.assertEqual(c.movimiento.destino, self.bodega)
        self.assertIsNone(c.movimiento.origen)
        original.refresh_from_db()
        self.assertEqual(original.cantidad, Decimal('10'))

    def test_confirmada_reducir_retira_solo_diferencia(self):
        confirmar_entrada(self.entrada.pk, self.gestor)
        c = self.corregir('8')
        self.assertEqual(self.saldo(), Decimal('28'))
        self.assertEqual(c.movimiento.tipo, 'CORR_ENTRADA_RETIRO')
        self.assertEqual(c.movimiento.cantidad, Decimal('2'))
        self.assertEqual(c.movimiento.origen, self.bodega)
        self.assertIsNone(c.movimiento.destino)
        self.assertEqual(c.estado_entrada, 'CONFIRMADA')

    def test_reducir_tras_consumir_sin_stock_revierte_todo(self):
        confirmar_entrada(self.entrada.pk, self.gestor)
        consumo = ConsumoInventario.objects.create(cliente=self.cliente, ubicacion_origen=self.bodega, creado_por=self.gestor)
        DetalleConsumoInventario.objects.create(consumo=consumo, producto=self.producto, cantidad=28)
        confirmar_consumo(consumo.pk, self.gestor)
        with self.assertRaisesMessage(ValidationError, 'Stock insuficiente'):
            self.corregir('5')
        self.detalle.refresh_from_db()
        self.assertEqual(self.detalle.cantidad, Decimal('10'))
        self.assertEqual(self.saldo(), Decimal('2'))
        self.assertFalse(CorreccionCantidadEntrada.objects.exists())
        self.assertEqual(MovimientoInventario.objects.count(), 3)

    def test_puede_retirar_todo_saldo_disponible_hasta_cero(self):
        confirmar_entrada(self.entrada.pk, self.gestor)
        consumo = ConsumoInventario.objects.create(cliente=self.cliente, ubicacion_origen=self.bodega, creado_por=self.gestor)
        DetalleConsumoInventario.objects.create(consumo=consumo, producto=self.producto, cantidad=28)
        confirmar_consumo(consumo.pk, self.gestor)
        self.corregir('8')
        self.assertEqual(self.saldo(), Decimal('0'))

    def test_conserva_precios_descuento_y_costo_de_compra_original(self):
        confirmar_entrada(self.entrada.pk, self.gestor)
        original = self.original()
        fecha = timezone.now() - timedelta(days=60)
        MovimientoInventario.objects.filter(pk=original.pk).update(fecha_operacion=fecha)
        ProductoInventario.objects.filter(pk=self.producto.pk).update(precio_referencia=999, costo_neto_ultimo=888)
        c = self.corregir('8')
        self.producto.refresh_from_db(); self.detalle.refresh_from_db(); self.entrada.refresh_from_db()
        self.assertEqual(c.movimiento.precio_referencia_snapshot, Decimal('200'))
        self.assertEqual(c.movimiento.costo_neto_snapshot, Decimal('180'))
        self.assertEqual(c.movimiento.fecha_operacion, fecha)
        self.assertGreater(c.creado, fecha)
        self.assertEqual(self.producto.precio_referencia, Decimal('999'))
        self.assertEqual(self.producto.costo_neto_ultimo, Decimal('888'))
        self.assertEqual(self.detalle.porcentaje_descuento, Decimal('10'))
        self.assertEqual(self.detalle.total_neto, Decimal('1440'))
        self.assertEqual(self.entrada.numero_factura, 'FV-CORREGIR')
        self.assertEqual(self.entrada.fecha_factura, date(2026, 10, 20))
        self.assertEqual(self.entrada.observaciones, 'Conservar observaciones')

    def test_usa_bodega_del_movimiento_original_tras_renombrarla(self):
        confirmar_entrada(self.entrada.pk, self.gestor)
        self.bodega.nombre = 'Bodega anterior'; self.bodega.save()
        otra = UbicacionInventario.objects.create(nombre='Bodega principal', tipo='BODEGA')
        c = self.corregir('13')
        self.assertEqual(c.movimiento.destino, self.bodega)
        self.assertEqual(self.saldo(), Decimal('33'))
        self.assertFalse(ExistenciaInventario.objects.filter(producto=self.producto, ubicacion=otra).exists())

    def test_confirmada_sin_movimiento_original_no_se_inventa_stock(self):
        EntradaInventario.objects.filter(pk=self.entrada.pk).update(estado='CONFIRMADA')
        with self.assertRaisesMessage(ValidationError, 'movimiento de compra válido'):
            self.corregir('13')
        self.assertEqual(self.saldo(), Decimal('20'))
        self.assertFalse(CorreccionCantidadEntrada.objects.exists())

    def test_original_de_otro_producto_se_rechaza(self):
        confirmar_entrada(self.entrada.pk, self.gestor)
        otro = ProductoInventario.objects.create(accesorio=Accesorio.objects.create(codigo='ZE02', descripcion='Otro'))
        MovimientoInventario.objects.filter(pk=self.original().pk).update(producto=otro)
        with self.assertRaises(ValidationError):
            self.corregir('13')
        self.assertFalse(CorreccionCantidadEntrada.objects.exists())

    def test_doble_envio_no_duplica_movimiento(self):
        confirmar_entrada(self.entrada.pk, self.gestor)
        self.corregir('13')
        with self.assertRaisesMessage(ValidationError, 'ya fue corregida'):
            self.corregir('13')
        self.assertEqual(self.saldo(), Decimal('33'))
        self.assertEqual(CorreccionCantidadEntrada.objects.count(), 1)

    def test_revisiones_sucesivas_y_proteccion_de_formulario_antiguo(self):
        confirmar_entrada(self.entrada.pk, self.gestor)
        c = self.corregir('8')
        self.corregir('10', revision=c.pk)
        with self.assertRaises(ValidationError):
            self.corregir('12')
        self.assertEqual(self.saldo(), Decimal('30'))
        self.assertEqual(CorreccionCantidadEntrada.objects.count(), 2)

    def test_misma_cantidad_rechazada(self):
        with self.assertRaisesMessage(ValidationError, 'diferente'):
            self.corregir('10')
        self.assertFalse(CorreccionCantidadEntrada.objects.exists())

    def test_cantidades_y_motivos_invalidos(self):
        for cantidad in ('', 'abc', 'NaN', 'Infinity', '0', '-1', '1.234', '1000000000000'):
            with self.subTest(cantidad=cantidad), self.assertRaises(ValidationError):
                self.corregir(cantidad)
        for motivo in ('', '    ', 'abc', 'x' * 1001):
            with self.subTest(motivo=motivo), self.assertRaises(ValidationError):
                self.corregir('8', motivo=motivo)
        self.assertFalse(CorreccionCantidadEntrada.objects.exists())

    def test_cantidad_decimal_admitida(self):
        confirmar_entrada(self.entrada.pk, self.gestor)
        c = self.corregir('8.25')
        self.assertEqual(self.saldo(), Decimal('28.25'))
        self.assertEqual(c.movimiento.cantidad, Decimal('1.75'))

    def test_servicio_rechaza_lectores_externos_e_inactivos(self):
        for usuario in (self.gerencia, self.externo):
            with self.subTest(usuario=usuario), self.assertRaises(PermissionDenied):
                self.corregir('8', usuario=usuario)
        self.gestor.is_active = False
        with self.assertRaises(PermissionDenied):
            self.corregir('8')
        self.assertFalse(CorreccionCantidadEntrada.objects.exists())

    def test_estado_no_admitido(self):
        EntradaInventario.objects.filter(pk=self.entrada.pk).update(estado='ANULADA')
        with self.assertRaisesMessage(ValidationError, 'estado'):
            self.corregir('8')

    def test_get_no_muta_post_guarda_y_muestra_historial(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertFalse(CorreccionCantidadEntrada.objects.exists())
        r = self.client.post(self.url, {'cantidad': '8', 'motivo': 'Se recibieron ocho', 'revision': '0'}, follow=True)
        self.assertRedirects(r, self.ficha)
        self.assertContains(r, 'Se recibieron ocho')
        self.assertContains(r, 'Sin movimiento: borrador')

    def test_errores_de_validacion_visibles_no_guardan(self):
        for datos in ({'cantidad': '', 'motivo': 'Cantidad recibida', 'revision': '0'},
                      {'cantidad': '8', 'motivo': 'abc', 'revision': '0'},
                      {'cantidad': '8', 'motivo': 'Cantidad recibida'}):
            r = self.client.post(self.url, datos)
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.context['form'].errors)
        self.assertFalse(CorreccionCantidadEntrada.objects.exists())

    def test_post_confirmada_muestra_movimiento_y_rechaza_revision_antigua(self):
        confirmar_entrada(self.entrada.pk, self.gestor)
        datos = {'cantidad': '8', 'motivo': 'Se recibieron ocho unidades', 'revision': '0'}
        r = self.client.post(self.url, datos, follow=True)
        self.assertRedirects(r, self.ficha)
        self.assertContains(r, 'Corrección de entrada: retiro')
        self.assertContains(r, 'Bodega principal')
        self.assertContains(r, 'Se recibieron ocho unidades')
        r = self.client.post(self.url, datos)
        self.assertContains(r, 'ya fue corregida')
        self.assertEqual(CorreccionCantidadEntrada.objects.count(), 1)
        self.assertEqual(self.saldo(), Decimal('28'))

    def test_error_stock_visible_en_formulario(self):
        confirmar_entrada(self.entrada.pk, self.gestor)
        ExistenciaInventario.objects.filter(producto=self.producto, ubicacion=self.bodega).update(cantidad=0)
        r = self.client.post(self.url, {'cantidad': '8', 'motivo': 'Se recibieron ocho unidades', 'revision': '0'})
        self.assertContains(r, 'Stock insuficiente')
        self.assertFalse(CorreccionCantidadEntrada.objects.exists())

    def test_detalle_de_otra_entrada_no_se_puede_corregir(self):
        otra = EntradaInventario.objects.create(proveedor=self.proveedor, numero_factura='OTRA', fecha_factura=date.today(), creado_por=self.gestor)
        url = reverse('inventario:corregir_cantidad_entrada', args=[otra.pk, self.detalle.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, {'cantidad': '8', 'motivo': 'Cambiar cantidad', 'revision': '0'}).status_code, 404)

    def test_gerencia_consulta_sin_corregir(self):
        self.client.force_login(self.gerencia)
        self.assertEqual(self.client.get(self.lista).status_code, 200)
        self.assertNotContains(self.client.get(self.ficha), 'Corregir cantidad')
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, {}).status_code, 403)

    def test_externos_sin_acceso_y_anonimo_a_login(self):
        self.client.force_login(self.externo)
        for url in (self.lista, self.ficha, self.url):
            self.assertEqual(self.client.get(url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.lista).status_code, 302)

    def test_csrf_y_metodos_http(self):
        cliente = Client(enforce_csrf_checks=True); cliente.force_login(self.gestor)
        self.assertEqual(cliente.post(self.url, {'cantidad': '8', 'motivo': 'Cantidad recibida', 'revision': '0'}).status_code, 403)
        self.assertEqual(self.client.delete(self.url).status_code, 405)
        self.assertEqual(self.client.post(self.lista).status_code, 405)
        self.assertEqual(self.client.post(self.ficha).status_code, 405)

    def test_busqueda_proveedor_nit_factura_numero_y_fechas(self):
        for q in ('CORRECCIONES', '9019876', 'FV-CORREGIR', str(self.entrada.pk)):
            r = self.client.get(self.lista, {'q': q})
            self.assertEqual(r.context['pagina'].paginator.count, 1)
        r = self.client.get(self.lista, {'desde': '2026-10-20', 'hasta': '2026-10-20', 'estado': 'BORRADOR'})
        self.assertEqual(r.context['pagina'].paginator.count, 1)
        self.assertEqual(self.client.get(self.lista, {'estado': 'CONFIRMADA'}).context['pagina'].paginator.count, 0)

    def test_filtros_invalidos_no_muestran_todo(self):
        for datos in ({'desde': '2026-11-20', 'hasta': '2026-10-20'}, {'estado': 'inventado'}, {'desde': 'ayer'}):
            r = self.client.get(self.lista, datos)
            self.assertTrue(r.context['form'].errors)
            self.assertEqual(r.context['pagina'].paginator.count, 0)
        for q in ('9' * 150, '²'):
            self.assertEqual(self.client.get(self.lista, {'q': q}).status_code, 200)

    def test_paginacion_y_motivo_escapado(self):
        for i in range(27):
            EntradaInventario.objects.create(proveedor=self.proveedor, numero_factura=f'FV-{i}', fecha_factura=date(2026, 10, 20), creado_por=self.gestor)
        self.assertEqual(len(self.client.get(self.lista).context['pagina']), 25)
        self.assertEqual(len(self.client.get(self.lista, {'page': 2}).context['pagina']), 3)
        self.assertEqual(self.client.get(self.lista, {'page': 'abc'}).status_code, 200)
        self.corregir('8', motivo='<script>alert(1)</script>')
        r = self.client.get(self.ficha)
        self.assertContains(r, '&lt;script&gt;')
        self.assertNotContains(r, '<script>alert(1)</script>')

    def test_historial_protege_el_detalle(self):
        self.corregir('8')
        with self.assertRaises(ProtectedError):
            self.detalle.delete()

    def test_fallo_del_movimiento_revierte_historial_y_cantidad(self):
        confirmar_entrada(self.entrada.pk, self.gestor)
        with patch('inventario.correcciones_entradas.registrar_movimiento', side_effect=ValidationError('Fallo de prueba')):
            with self.assertRaises(ValidationError):
                self.corregir('8')
        self.detalle.refresh_from_db()
        self.assertEqual(self.detalle.cantidad, Decimal('10'))
        self.assertEqual(self.saldo(), Decimal('30'))
        self.assertFalse(CorreccionCantidadEntrada.objects.exists())

    def test_confirmar_de_nuevo_no_reingresa_tras_correccion(self):
        confirmar_entrada(self.entrada.pk, self.gestor)
        self.corregir('8')
        confirmar_entrada(self.entrada.pk, self.gestor)
        self.assertEqual(self.saldo(), Decimal('28'))
        self.assertEqual(MovimientoInventario.objects.count(), 3)

    def test_links_tablero_y_consumos_se_conservan(self):
        r = self.client.get(reverse('inventario:tablero'))
        self.assertContains(r, self.lista)
        self.assertContains(r, self.ficha)
        self.assertContains(r, reverse('inventario:lista_consumos'))
