from decimal import Decimal
import time
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase
from django.urls import reverse

from operacion.models import Accesorio
from .conteo_qr import SALT_CONFIRMAR, VIGENCIA, confirmar_conteo
from .models import ExistenciaInventario, MovimientoInventario, ProductoInventario, UbicacionInventario
from .servicios import fijar_saldo_inicial, obtener_bodega_principal, registrar_movimiento


class ConteoQRTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.gestor = User.objects.create_user('qr_gestor')
        cls.otro_gestor = User.objects.create_user('qr_otro')
        grupo = Group.objects.create(name='GESTION_INVENTARIO')
        cls.gestor.groups.add(grupo); cls.otro_gestor.groups.add(grupo)
        cls.gerencia = User.objects.create_user('qr_gerencia')
        cls.gerencia.groups.add(Group.objects.create(name='GESTION_GERENCIA'))
        cls.externo = User.objects.create_user('qr_externo')
        cls.producto = ProductoInventario.objects.create(accesorio=Accesorio.objects.create(codigo='A012', descripcion='MACHO 1"', activo=True))
        cls.bodega = obtener_bodega_principal()
        fijar_saldo_inicial(producto=cls.producto, cantidad=20, precio_referencia=100,
                           unidad_medida='UNID', usuario=cls.gestor, origen='qr_test')

    def setUp(self):
        self.client.force_login(self.gestor)
        self.lector = reverse('inventario:lector_qr')
        self.url = reverse('inventario:conteo_qr_producto', args=[self.producto.pk, self.bodega.pk])

    def saldo(self):
        return ExistenciaInventario.objects.get(producto=self.producto, ubicacion=self.bodega).cantidad

    def revision(self):
        return self.client.get(self.url).context['form'].initial['revision']

    def revisar(self, cantidad='18', motivo='Conteo de todas las cajas', revision=None):
        return self.client.post(self.url, {'accion': 'revisar', 'cantidad_fisica': cantidad,
                                         'motivo': motivo, 'revision': revision or self.revision()})

    def confirmar(self, token, url=None):
        return self.client.post(url or self.url, {'accion': 'confirmar', 'confirmacion': token})

    def mover(self, cantidad=1, origen=None, destino=None):
        return registrar_movimiento(producto=self.producto, tipo='TRASLADO' if origen else 'AJUSTE_ENTRADA',
                                    cantidad=cantidad, origen=origen, destino=destino or (None if origen else self.bodega), usuario=self.gestor)

    def test_lector_inicial_y_consulta_no_escriben(self):
        self.assertEqual(self.client.get(self.lector).status_code, 200)
        r = self.client.get(self.url)
        self.assertEqual(r.context['saldo'], Decimal('20'))
        self.assertContains(r, 'Existencia registrada')
        self.assertContains(r, 'todas las unidades')
        self.assertContains(r, 'Revisar diferencia')
        self.assertEqual(self.saldo(), Decimal('20'))
        self.assertEqual(MovimientoInventario.objects.count(), 1)

    def test_codigo_normalizado_redirige_a_bodega_unica(self):
        self.assertRedirects(self.client.get(self.lector, {'codigo': ' a012 '}), self.url)

    def test_codigo_desconocido_muestra_error(self):
        r = self.client.get(self.lector, {'codigo': 'A999'})
        self.assertContains(r, 'No se encontró un accesorio activo')
        self.assertEqual(MovimientoInventario.objects.count(), 1)

    def test_qr_ajeno_url_o_codigo_invalido_no_redirigen(self):
        for codigo in ('https://ejemplo.com', '<script>', 'A 012', 'Á012', 'x' * 41, ''):
            with self.subTest(codigo=codigo):
                r = self.client.get(self.lector, {'codigo': codigo})
                self.assertEqual(r.status_code, 200)
                self.assertTrue(r.context['form'].errors)

    def test_varias_bodegas_exigen_elegir_y_excluyen_otras_ubicaciones(self):
        otra = UbicacionInventario.objects.create(nombre='Bodega secundaria', tipo='BODEGA', activa=True)
        UbicacionInventario.objects.create(nombre='Inactiva', tipo='BODEGA', activa=False)
        UbicacionInventario.objects.create(nombre='Ubicación técnico', tipo='TECNICO', activa=True)
        r = self.client.get(self.lector, {'codigo': 'A012'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual({b.pk for b in r.context['bodegas']}, {self.bodega.pk, otra.pk})
        self.assertContains(r, reverse('inventario:conteo_qr_producto', args=[self.producto.pk, otra.pk]))

    def test_sin_bodegas_activas_no_crea_nuevas(self):
        UbicacionInventario.objects.update(activa=False)
        r = self.client.get(self.lector, {'codigo': 'A012'})
        self.assertContains(r, 'No hay bodegas activas')
        self.assertEqual(UbicacionInventario.objects.count(), 1)

    def test_producto_inactivo_o_accesorio_inactivo_no_se_cuenta(self):
        ProductoInventario.objects.filter(pk=self.producto.pk).update(activo=False)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertTrue(self.client.get(self.lector, {'codigo': 'A012'}).context['form'].errors)
        ProductoInventario.objects.filter(pk=self.producto.pk).update(activo=True)
        Accesorio.objects.filter(pk=self.producto.accesorio_id).update(activo=False)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_bodega_inactiva_y_ubicacion_tecnico_no_se_cuentan(self):
        UbicacionInventario.objects.filter(pk=self.bodega.pk).update(activa=False)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        ubicacion = UbicacionInventario.objects.create(nombre='Técnico QR', tipo='TECNICO')
        url = reverse('inventario:conteo_qr_producto', args=[self.producto.pk, ubicacion.pk])
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_previsualizar_muestra_diferencia_sin_guardar(self):
        r = self.revisar('18')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['diferencia'], Decimal('-2'))
        self.assertContains(r, 'Confirmar ajuste de inventario')
        self.assertEqual(self.saldo(), Decimal('20'))
        self.assertEqual(MovimientoInventario.objects.count(), 1)

    def test_confirmar_reduccion_y_trazabilidad(self):
        token = self.revisar('18').context['confirmacion']
        self.assertRedirects(self.confirmar(token), self.url)
        self.assertEqual(self.saldo(), Decimal('18'))
        m = MovimientoInventario.objects.exclude(tipo='SALDO_INICIAL').get()
        self.assertEqual(m.tipo, 'AJUSTE_SALIDA')
        self.assertEqual(m.cantidad, Decimal('2'))
        self.assertEqual(m.origen, self.bodega)
        self.assertEqual(m.registrado_por, self.gestor)
        self.assertIn('Saldo anterior: 20', m.observaciones)
        self.assertIn('Saldo físico: 18', m.observaciones)
        self.assertIn('Conteo de todas las cajas', m.observaciones)
        self.assertIn('Código A012', m.observaciones)

    def test_confirmar_aumento_solo_diferencia(self):
        token = self.revisar('23.50').context['confirmacion']
        self.confirmar(token)
        self.assertEqual(self.saldo(), Decimal('23.50'))
        m = MovimientoInventario.objects.exclude(tipo='SALDO_INICIAL').get()
        self.assertEqual(m.tipo, 'AJUSTE_ENTRADA')
        self.assertEqual(m.cantidad, Decimal('3.50'))
        self.assertEqual(m.destino, self.bodega)

    def test_cero_es_conteo_valido(self):
        self.confirmar(self.revisar('0').context['confirmacion'])
        self.assertEqual(self.saldo(), Decimal('0'))
        self.assertEqual(MovimientoInventario.objects.exclude(tipo='SALDO_INICIAL').get().cantidad, Decimal('20'))

    def test_cantidad_igual_no_crea_ajuste(self):
        r = self.revisar('20')
        self.assertContains(r, 'Finalizar sin ajuste')
        ex = ExistenciaInventario.objects.get(producto=self.producto, ubicacion=self.bodega)
        fecha = ex.actualizado
        r = self.confirmar(r.context['confirmacion'])
        self.assertRedirects(r, self.url)
        ex.refresh_from_db()
        self.assertEqual(ex.actualizado, fecha)
        self.assertEqual(MovimientoInventario.objects.count(), 1)

    def test_producto_sin_existencia_consulta_y_revision_son_solo_lectura(self):
        otro = ProductoInventario.objects.create(accesorio=Accesorio.objects.create(codigo='A014', descripcion='MACHO 1 1/2"'))
        url = reverse('inventario:conteo_qr_producto', args=[otro.pk, self.bodega.pk])
        r = self.client.get(url)
        self.assertEqual(r.context['saldo'], 0)
        self.assertFalse(ExistenciaInventario.objects.filter(producto=otro).exists())
        datos = {'accion': 'revisar', 'cantidad_fisica': '5', 'motivo': 'Conteo inicial de todas las cajas', 'revision': r.context['form'].initial['revision']}
        r = self.client.post(url, datos)
        self.assertFalse(ExistenciaInventario.objects.filter(producto=otro).exists())
        self.confirmar(r.context['confirmacion'], url=url)
        self.assertEqual(ExistenciaInventario.objects.get(producto=otro).cantidad, Decimal('5'))

    def test_cantidad_y_motivo_invalidos_sin_confirmacion(self):
        for cantidad in ('', '-1', 'NaN', 'Infinity', 'abc', '1.234', '1000000000000'):
            with self.subTest(cantidad=cantidad):
                r = self.revisar(cantidad)
                self.assertTrue(r.context['form'].errors)
                self.assertNotIn('confirmacion', r.context)
        for motivo in ('', 'abc', '  ', 'x' * 1001):
            self.assertTrue(self.revisar(motivo=motivo).context['form'].errors)
        self.assertEqual(self.saldo(), Decimal('20'))

    def test_revision_alterada_no_se_acepta(self):
        r = self.revisar(revision='token-inventado')
        self.assertContains(r, 'no es válido')
        self.assertNotIn('confirmacion', r.context)

    def test_revision_vencida(self):
        revision = self.revision()
        futuro = time.time() + VIGENCIA + 2
        with patch('django.core.signing.time.time', return_value=futuro):
            r = self.revisar(revision=revision)
        self.assertContains(r, 'venció')

    def test_cambio_antes_de_revisar_rechaza_saldo_antiguo(self):
        revision = self.revision()
        self.mover()
        r = self.revisar(revision=revision)
        self.assertContains(r, 'existencia cambió')
        self.assertNotIn('confirmacion', r.context)
        self.assertEqual(self.saldo(), Decimal('21'))

    def test_cambio_tras_revisar_rechaza_confirmacion(self):
        token = self.revisar().context['confirmacion']
        self.mover(3)
        r = self.confirmar(token)
        self.assertContains(r, 'existencia cambió')
        self.assertEqual(self.saldo(), Decimal('23'))
        self.assertEqual(MovimientoInventario.objects.count(), 2)

    def test_saldo_vuelve_al_anterior_pero_version_cambio(self):
        token = self.revisar().context['confirmacion']
        self.mover(1)
        self.mover(1, origen=self.bodega)
        self.assertEqual(self.saldo(), Decimal('20'))
        self.assertContains(self.confirmar(token), 'existencia cambió')
        self.assertEqual(MovimientoInventario.objects.count(), 3)

    def test_reenviar_confirmacion_no_duplica_ajuste(self):
        token = self.revisar().context['confirmacion']
        self.assertEqual(self.confirmar(token).status_code, 302)
        self.assertContains(self.confirmar(token), 'existencia cambió')
        self.assertEqual(self.saldo(), Decimal('18'))
        self.assertEqual(MovimientoInventario.objects.count(), 2)

    def test_token_final_alterado_o_vencido(self):
        token = self.revisar().context['confirmacion']
        self.assertContains(self.confirmar(token + 'x'), 'no es válido')
        futuro = time.time() + VIGENCIA + 2
        with patch('django.core.signing.time.time', return_value=futuro):
            self.assertContains(self.confirmar(token), 'venció')
        self.assertEqual(self.saldo(), Decimal('20'))

    def test_token_no_puede_reutilizarse_por_otro_gestor(self):
        token = self.revisar().context['confirmacion']
        self.client.force_login(self.otro_gestor)
        self.assertContains(self.confirmar(token), 'no corresponde')
        self.assertEqual(self.saldo(), Decimal('20'))

    def test_token_no_cambia_de_bodega_ni_producto(self):
        token = self.revisar().context['confirmacion']
        bodega = UbicacionInventario.objects.create(nombre='Otra bodega', tipo='BODEGA')
        otro = ProductoInventario.objects.create(accesorio=Accesorio.objects.create(codigo='A013', descripcion='Otro macho'))
        for p, b in ((self.producto.pk, bodega.pk), (otro.pk, self.bodega.pk)):
            r = self.confirmar(token, url=reverse('inventario:conteo_qr_producto', args=[p, b]))
            self.assertContains(r, 'no corresponde')
        self.assertEqual(self.saldo(), Decimal('20'))
        self.assertFalse(ExistenciaInventario.objects.filter(producto=otro).exists())

    def test_cantidad_de_confirmacion_procede_del_token_no_del_post(self):
        token = self.revisar('18').context['confirmacion']
        self.client.post(self.url, {'accion': 'confirmar', 'confirmacion': token, 'cantidad_fisica': '999', 'motivo': 'Motivo alterado'})
        self.assertEqual(self.saldo(), Decimal('18'))
        self.assertNotIn('Motivo alterado', MovimientoInventario.objects.exclude(tipo='SALDO_INICIAL').get().observaciones)

    def test_gerencia_consulta_pero_no_ajusta(self):
        token = self.revisar().context['confirmacion']
        self.client.force_login(self.gerencia)
        self.assertEqual(self.client.get(self.lector).status_code, 200)
        r = self.client.get(self.url)
        self.assertContains(r, 'permiso de consulta')
        self.assertNotContains(r, 'Revisar diferencia')
        self.assertEqual(self.revisar().status_code, 403)
        self.assertEqual(self.confirmar(token).status_code, 403)

    def test_externo_y_anonimo_no_acceden(self):
        self.client.force_login(self.externo)
        for url in (self.lector, self.url):
            self.assertEqual(self.client.get(url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.lector).status_code, 302)

    def test_servicio_rechaza_inactivos_y_no_gestores(self):
        token = self.revisar().context['confirmacion']
        for usuario in (self.gerencia, self.externo):
            with self.assertRaises(PermissionDenied):
                confirmar_conteo(token=token, producto_id=self.producto.pk, ubicacion_id=self.bodega.pk, usuario=usuario)
        self.gestor.is_active = False
        with self.assertRaises(PermissionDenied):
            confirmar_conteo(token=token, producto_id=self.producto.pk, ubicacion_id=self.bodega.pk, usuario=self.gestor)

    def test_csrf_y_metodos_http(self):
        cliente = Client(enforce_csrf_checks=True); cliente.force_login(self.gestor)
        self.assertEqual(cliente.post(self.url, {'accion': 'confirmar', 'confirmacion': 'x'}).status_code, 403)
        self.assertEqual(self.client.post(self.lector, {}).status_code, 405)
        self.assertEqual(self.client.put(self.url, {}).status_code, 405)

    def test_no_hay_confirmacion_directa_sin_token_o_accion_valida(self):
        self.assertContains(self.client.post(self.url, {'accion': 'confirmar'}), 'no es válido')
        self.assertContains(self.client.post(self.url, {'accion': 'inventada'}), 'Acción no válida')
        self.assertEqual(MovimientoInventario.objects.count(), 1)

    def test_error_de_ajuste_no_guarda_cantidad(self):
        token = self.revisar().context['confirmacion']
        with patch('inventario.conteo_qr.ajustar_existencia', side_effect=ValidationError('Fallo de prueba')):
            self.assertContains(self.confirmar(token), 'Fallo de prueba')
        self.assertEqual(self.saldo(), Decimal('20'))
        self.assertEqual(MovimientoInventario.objects.count(), 1)

    def test_producto_desactivado_despues_de_revision(self):
        token = self.revisar().context['confirmacion']
        ProductoInventario.objects.filter(pk=self.producto.pk).update(activo=False)
        self.assertEqual(self.confirmar(token).status_code, 404)
        self.assertEqual(self.saldo(), Decimal('20'))

    def test_texto_motivo_se_escapa_y_no_cachea(self):
        r = self.revisar(motivo='<script>alert(1)</script>')
        self.assertContains(r, '&lt;script&gt;')
        self.assertNotContains(r, '<script>alert(1)</script>')
        self.assertIn('no-store', r['Cache-Control'])
        self.assertIn('no-store', self.client.get(self.url)['Cache-Control'])

    def test_lectura_tiene_alternativas_locales_y_enlace_tablero(self):
        r = self.client.get(self.lector)
        self.assertContains(r, 'Abrir cámara')
        self.assertContains(r, 'Leer una foto del QR')
        self.assertContains(r, '/static/inventario/vendor/jsQR-1.4.0.js')
        self.assertContains(self.client.get(reverse('inventario:tablero')), self.lector)

    def test_ajuste_en_segunda_bodega_no_modifica_principal(self):
        bodega = UbicacionInventario.objects.create(nombre='Segunda', tipo='BODEGA')
        url = reverse('inventario:conteo_qr_producto', args=[self.producto.pk, bodega.pk])
        r = self.client.get(url)
        r = self.client.post(url, {'accion': 'revisar', 'cantidad_fisica': '7', 'motivo': 'Conteo de segunda bodega', 'revision': r.context['form'].initial['revision']})
        self.confirmar(r.context['confirmacion'], url=url)
        self.assertEqual(ExistenciaInventario.objects.get(producto=self.producto, ubicacion=bodega).cantidad, Decimal('7'))
        self.assertEqual(self.saldo(), Decimal('20'))
