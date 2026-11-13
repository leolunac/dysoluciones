from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from operacion.models import Accesorio, Cliente
from .correcciones import corregir_cantidad
from .models import ConsumoInventario, CorreccionCantidadConsumo, DetalleConsumoInventario, ExistenciaInventario, MovimientoInventario, ProductoInventario
from .servicios import confirmar_consumo, fijar_saldo_inicial, obtener_bodega_principal


class CorreccionesConsumoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.gestor = User.objects.create_user('gestor_correcciones')
        cls.gestor.groups.add(Group.objects.create(name='GESTION_INVENTARIO'))
        cls.gerencia = User.objects.create_user('lector_correcciones')
        cls.gerencia.groups.add(Group.objects.create(name='GESTION_GERENCIA'))
        cls.externo = User.objects.create_user('cliente_correcciones')
        cls.cliente = Cliente.objects.create(nombre='UNIDAD CORRECCIONES', nit='9012345', activo=True)
        cls.bodega = obtener_bodega_principal()
        accesorio = Accesorio.objects.create(codigo='ZC01', descripcion='UNION CORRECCIONES', activo=True)
        cls.producto = ProductoInventario.objects.create(accesorio=accesorio, precio_referencia=Decimal('100'))
        fijar_saldo_inicial(producto=cls.producto, cantidad=20, precio_referencia=100,
                           unidad_medida='UNID', usuario=cls.gestor, origen='correcciones_test')
        cls.consumo = ConsumoInventario.objects.create(cliente=cls.cliente, ubicacion_origen=cls.bodega,
                                                       creado_por=cls.gestor, observaciones='No cambiar')
        cls.detalle = DetalleConsumoInventario.objects.create(consumo=cls.consumo, producto=cls.producto, cantidad=5)

    def setUp(self):
        self.client.force_login(self.gestor)
        self.lista = reverse('inventario:lista_consumos')
        self.url = reverse('inventario:corregir_cantidad_consumo', args=[self.consumo.pk, self.detalle.pk])
        self.ficha = reverse('inventario:detalle_consumo', args=[self.consumo.pk])

    def corregir(self, cantidad, **kwargs):
        return corregir_cantidad(consumo_id=self.consumo.pk, detalle_id=self.detalle.pk,
                                 cantidad=cantidad, motivo='Error al digitar cantidad', revision=0,
                                 usuario=self.gestor, **kwargs)

    def saldo(self):
        return ExistenciaInventario.objects.get(producto=self.producto, ubicacion=self.bodega).cantidad

    def test_borrador_actualiza_y_audita_sin_mover_existencias(self):
        cambio = self.corregir('2')
        self.detalle.refresh_from_db()
        self.assertEqual(self.detalle.cantidad, Decimal('2'))
        self.assertEqual(self.saldo(), Decimal('20'))
        self.assertIsNone(cambio.movimiento_id)
        self.assertEqual((cambio.cantidad_anterior, cambio.cantidad_nueva), (Decimal('5'), Decimal('2')))
        self.assertEqual(cambio.registrado_por, self.gestor)
        self.assertEqual(cambio.estado_consumo, 'BORRADOR')
        self.assertEqual(MovimientoInventario.objects.count(), 1)

    def test_confirmar_borrador_descuenta_cantidad_corregida(self):
        self.corregir('2')
        confirmar_consumo(self.consumo.pk, self.gestor)
        self.assertEqual(self.saldo(), Decimal('18'))
        self.assertEqual(MovimientoInventario.objects.get(tipo='CONSUMO').cantidad, Decimal('2'))

    def test_confirmado_reducir_devuelve_diferencia_y_conserva_original(self):
        confirmar_consumo(self.consumo.pk, self.gestor)
        original = MovimientoInventario.objects.get(tipo='CONSUMO')
        antes = (original.cantidad, original.creado, original.precio_referencia_snapshot)
        cambio = self.corregir('2')
        self.assertEqual(self.saldo(), Decimal('18'))
        self.assertEqual(cambio.movimiento.tipo, 'CORR_CONSUMO_ENTRADA')
        self.assertEqual(cambio.movimiento.cantidad, Decimal('3'))
        self.assertEqual(cambio.movimiento.destino, self.bodega)
        original.refresh_from_db()
        self.assertEqual((original.cantidad, original.creado, original.precio_referencia_snapshot), antes)

    def test_confirmado_aumentar_descuenta_solo_diferencia(self):
        confirmar_consumo(self.consumo.pk, self.gestor)
        cambio = self.corregir('8')
        self.assertEqual(self.saldo(), Decimal('12'))
        self.assertEqual(cambio.movimiento.tipo, 'CORR_CONSUMO_SALIDA')
        self.assertEqual(cambio.movimiento.cantidad, Decimal('3'))

    def test_stock_insuficiente_revierte_correccion_completa(self):
        confirmar_consumo(self.consumo.pk, self.gestor)
        with self.assertRaises(ValidationError):
            self.corregir('21')
        self.detalle.refresh_from_db()
        self.assertEqual(self.detalle.cantidad, Decimal('5'))
        self.assertEqual(self.saldo(), Decimal('15'))
        self.assertEqual(CorreccionCantidadConsumo.objects.count(), 0)
        self.assertEqual(MovimientoInventario.objects.count(), 2)

    def test_doble_envio_y_revision_antigua_no_descuentan_dos_veces(self):
        confirmar_consumo(self.consumo.pk, self.gestor)
        self.corregir('8')
        with self.assertRaises(ValidationError):
            self.corregir('8')
        self.assertEqual(self.saldo(), Decimal('12'))
        self.assertEqual(CorreccionCantidadConsumo.objects.count(), 1)

    def test_correcciones_sucesivas_y_retorno_a_cantidad_inicial(self):
        confirmar_consumo(self.consumo.pk, self.gestor)
        cambio = self.corregir('2')
        segundo = corregir_cantidad(consumo_id=self.consumo.pk, detalle_id=self.detalle.pk,
                                    cantidad=5, motivo='Cantidad verificada en campo', revision=cambio.pk, usuario=self.gestor)
        self.assertEqual(self.saldo(), Decimal('15'))
        with self.assertRaises(ValidationError):
            self.corregir('2')
        self.assertEqual(CorreccionCantidadConsumo.objects.count(), 2)
        self.assertNotEqual(cambio.pk, segundo.pk)

    def test_sin_cambio_no_crea_historial(self):
        with self.assertRaises(ValidationError):
            self.corregir('5')
        self.assertEqual(CorreccionCantidadConsumo.objects.count(), 0)

    def test_valores_invalidos_y_motivo_obligatorio(self):
        for valor in ('', 'abc', 'NaN', 'Infinity', '0', '-1', '1.234', '9999999999999999'):
            with self.subTest(valor=valor), self.assertRaises(ValidationError):
                self.corregir(valor)
        for motivo in ('', '    ', 'abc'):
            with self.subTest(motivo=motivo), self.assertRaises(ValidationError):
                corregir_cantidad(consumo_id=self.consumo.pk, detalle_id=self.detalle.pk, cantidad=2,
                                   motivo=motivo, revision=0, usuario=self.gestor)
        self.assertEqual(CorreccionCantidadConsumo.objects.count(), 0)

    def test_fecha_y_precio_historicos_se_conservan(self):
        antigua = timezone.now() - timedelta(days=60)
        ConsumoInventario.objects.filter(pk=self.consumo.pk).update(fecha=antigua)
        confirmar_consumo(self.consumo.pk, self.gestor)
        ProductoInventario.objects.filter(pk=self.producto.pk).update(precio_referencia=999)
        cambio = self.corregir('2')
        self.assertEqual(cambio.movimiento.precio_referencia_snapshot, Decimal('100'))
        self.assertEqual(cambio.movimiento.fecha_operacion, antigua)
        self.assertGreater(cambio.creado, antigua)
        self.consumo.refresh_from_db()
        self.assertEqual(self.consumo.observaciones, 'No cambiar')
        self.assertEqual(self.consumo.fecha, antigua)

    def test_usuario_sin_permiso_no_puede_corregir_por_servicio(self):
        for usuario in (self.gerencia, self.externo):
            with self.assertRaises(PermissionDenied):
                corregir_cantidad(consumo_id=self.consumo.pk, detalle_id=self.detalle.pk,
                                   cantidad=2, motivo='Prueba de permisos', revision=0, usuario=usuario)

    def test_usuario_inactivo_no_corrige(self):
        self.gestor.is_active = False
        with self.assertRaises(PermissionDenied):
            self.corregir('2')

    def test_get_no_modifica_y_post_redirige_a_detalle(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(CorreccionCantidadConsumo.objects.count(), 0)
        response = self.client.post(self.url, {'cantidad':'2','motivo':'Error de digitación','revision':'0'})
        self.assertRedirects(response, self.ficha)
        self.assertContains(self.client.get(self.ficha), 'Error de digitación')

    def test_error_stock_visible_y_revision_conservada(self):
        confirmar_consumo(self.consumo.pk, self.gestor)
        response = self.client.post(self.url, {'cantidad':'21','motivo':'Error de digitación','revision':'0'})
        self.assertContains(response, 'Stock insuficiente')
        self.assertEqual(self.saldo(), Decimal('15'))

    def test_detalle_de_otro_consumo_devuelve_404(self):
        otro = ConsumoInventario.objects.create(cliente=self.cliente, ubicacion_origen=self.bodega, creado_por=self.gestor)
        url = reverse('inventario:corregir_cantidad_consumo', args=[otro.pk, self.detalle.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, {'cantidad':'2','motivo':'Error de digitación','revision':'0'}).status_code, 404)

    def test_gerencia_consulta_sin_boton_ni_permiso_para_editar(self):
        self.client.force_login(self.gerencia)
        self.assertEqual(self.client.get(self.lista).status_code, 200)
        self.assertNotContains(self.client.get(self.ficha), 'Corregir cantidad')
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, {'cantidad':'2','motivo':'Error de digitación','revision':'0'}).status_code, 403)

    def test_usuarios_externos_y_anonimos_no_consultan(self):
        self.client.force_login(self.externo)
        for url in (self.lista,self.ficha,self.url):
            self.assertEqual(self.client.get(url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.lista).status_code, 302)

    def test_csrf_y_metodos(self):
        seguro = Client(enforce_csrf_checks=True)
        seguro.force_login(self.gestor)
        self.assertEqual(seguro.post(self.url, {'cantidad':'2','motivo':'Error de digitación','revision':'0'}).status_code, 403)
        self.assertEqual(self.client.delete(self.url).status_code, 405)
        self.assertEqual(self.client.post(self.lista).status_code, 405)

    def test_lista_busqueda_nit_estado_y_fechas(self):
        self.assertContains(self.client.get(self.lista, {'q':'9012345'}), 'UNIDAD CORRECCIONES')
        self.assertNotContains(self.client.get(self.lista, {'estado':'CONFIRMADO'}), 'UNIDAD CORRECCIONES')
        self.assertContains(self.client.get(self.lista, {'q':str(self.consumo.pk)}), 'UNIDAD CORRECCIONES')
        self.assertContains(self.client.get(self.lista, {'desde':'2030-01-02','hasta':'2020-01-01'}), 'La fecha inicial')
        self.assertNotContains(self.client.get(self.lista, {'estado':'invalido'}), 'UNIDAD CORRECCIONES')
        self.assertEqual(self.client.get(self.lista, {'q':'9'*150}).status_code, 200)

    def test_paginacion_25_y_historial_escapado(self):
        ConsumoInventario.objects.bulk_create([ConsumoInventario(cliente=self.cliente, ubicacion_origen=self.bodega, creado_por=self.gestor) for _ in range(27)])
        self.assertEqual(len(self.client.get(self.lista).context['pagina']),25)
        self.assertEqual(len(self.client.get(self.lista,{'page':2}).context['pagina']),3)
        self.assertEqual(self.client.get(self.lista,{'page':'nada'}).status_code,200)
        corregir_cantidad(consumo_id=self.consumo.pk,detalle_id=self.detalle.pk,cantidad=2,motivo='<script>alert(1)</script>',revision=0,usuario=self.gestor)
        response=self.client.get(self.ficha)
        self.assertNotContains(response,'<script>alert(1)</script>')
        self.assertContains(response,'&lt;script&gt;')

    def test_historial_protege_borrado_del_detalle(self):
        self.corregir('2')
        with self.assertRaises(ProtectedError):
            self.detalle.delete()

    def test_excel_y_estadisticas_reflejan_consumo_neto(self):
        confirmar_consumo(self.consumo.pk,self.gestor)
        self.corregir('2')
        response=self.client.get(reverse('inventario:exportar_consumos'))
        ws=load_workbook(BytesIO(response.content)).active
        self.assertEqual(ws['E2'].value,5)
        self.assertEqual(ws['E3'].value,-3)
        self.assertEqual(ws['G4'].value,200)
        self.assertIn('Corrección',ws['D3'].value)
        tablero=self.client.get(reverse('inventario:tablero'))
        self.assertEqual(tablero.context['productos_mas_usados'][0]['total'],Decimal('2'))
        self.assertEqual(tablero.context['clientes_mayor_consumo'][0]['total'],Decimal('2'))
        self.assertContains(tablero,self.lista)

    def test_correccion_en_periodo_historico_no_afecta_ultimo_mes(self):
        antigua=timezone.now()-timedelta(days=60)
        ConsumoInventario.objects.filter(pk=self.consumo.pk).update(fecha=antigua)
        confirmar_consumo(self.consumo.pk,self.gestor)
        self.corregir('2')
        tablero=self.client.get(reverse('inventario:tablero'))
        self.assertEqual(list(tablero.context['productos_mas_usados']),[])
        response=self.client.get(reverse('inventario:exportar_consumos'),{'fecha_desde':antigua.date().isoformat(),'fecha_hasta':antigua.date().isoformat()})
        ws=load_workbook(BytesIO(response.content)).active
        self.assertEqual(ws['G4'].value,200)

    @patch('inventario.correcciones.registrar_movimiento',side_effect=ValidationError('Fallo simulado'))
    def test_rollback_de_movimiento_no_deja_auditoria_parcial(self,movimiento):
        confirmar_consumo(self.consumo.pk,self.gestor)
        with self.assertRaises(ValidationError):self.corregir('2')
        self.assertEqual(CorreccionCantidadConsumo.objects.count(),0)
        self.detalle.refresh_from_db()
        self.assertEqual(self.detalle.cantidad,Decimal('5'))
