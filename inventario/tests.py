from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from openpyxl import load_workbook

from operacion.models import (
    Accesorio,
    AccesorioActividad,
    ActividadTecnico,
    Cliente,
    DetalleRemision,
    RemisionTecnico,
    Tecnico,
)

from .models import (
    ConsumoInventario,
    DetalleConsumoInventario,
    DetalleEntradaInventario,
    EntradaInventario,
    ExistenciaInventario,
    MovimientoInventario,
    ProductoInventario,
    Proveedor,
    ReferenciaProveedor,
)
from .servicios import (
    ajustar_existencia,
    confirmar_consumo,
    confirmar_entrada,
    fijar_saldo_inicial,
    obtener_bodega_principal,
)
from .integracion_operacion import (
    obtener_ubicacion_tecnico,
    registrar_consumo_actividad,
    registrar_devolucion_detalle,
    registrar_entrega_remision,
)
from .management.commands.importar_inventario_anterior import leer_productos


class ImportadorAnteriorTest(SimpleTestCase):
    def test_interpreta_producto_del_respaldo_mysql(self):
        contenido = (
            "INSERT INTO `productos` VALUES "
            "('A001', 'UNION 1/2', 'UNID', 12.00, 3456.00, '2026-10-05');\n"
        )
        with TemporaryDirectory() as temporal:
            ruta = Path(temporal) / "inventario.sql"
            ruta.write_text(contenido, encoding="utf-8")
            productos = leer_productos(ruta)
        self.assertEqual(len(productos), 1)
        self.assertEqual(productos[0]["codigo"], "A001")
        self.assertEqual(productos[0]["cantidad"], Decimal("12.00"))
        self.assertEqual(productos[0]["precio"], Decimal("3456.00"))


class InventarioBaseTest(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_user("inventario", password="segura")
        grupo = Group.objects.create(name="GESTION_INVENTARIO")
        self.usuario.groups.add(grupo)
        self.cliente = Cliente.objects.create(
            nombre="UNIDAD PRUEBA",
            direccion="Calle 1",
            telefono_porteria="123",
            administrador="Administración",
            email="prueba@example.com",
            tipo_contrato="7X24",
            frecuencia_lavado=4,
        )
        accesorio = Accesorio.objects.create(
            codigo="A001",
            descripcion="UNIÓN DE PRUEBA",
            activo=True,
        )
        self.producto = ProductoInventario.objects.create(
            accesorio=accesorio,
            precio_referencia=Decimal("10000.00"),
        )
        self.bodega = obtener_bodega_principal()


class ServiciosInventarioTest(InventarioBaseTest):
    def test_entrada_conserva_precio_lista_y_costo_con_descuento(self):
        proveedor = Proveedor.objects.create(nombre="PROVEEDOR PRUEBA")
        entrada = EntradaInventario.objects.create(
            proveedor=proveedor,
            numero_factura="FV-1",
            fecha_factura=date(2026, 10, 5),
            creado_por=self.usuario,
        )
        DetalleEntradaInventario.objects.create(
            entrada=entrada,
            producto=self.producto,
            cantidad=Decimal("10.00"),
            precio_unitario_lista=Decimal("20000.00"),
            porcentaje_descuento=Decimal("10.00"),
        )

        confirmar_entrada(entrada.pk, self.usuario)

        self.producto.refresh_from_db()
        saldo = ExistenciaInventario.objects.get(
            producto=self.producto,
            ubicacion=self.bodega,
        )
        self.assertEqual(saldo.cantidad, Decimal("10.00"))
        self.assertEqual(self.producto.precio_referencia, Decimal("20000.00"))
        self.assertEqual(self.producto.costo_neto_ultimo, Decimal("18000.00"))

    def test_consumo_descuenta_y_guarda_unidad_y_valor(self):
        fijar_saldo_inicial(
            producto=self.producto,
            cantidad=Decimal("5.00"),
            precio_referencia=Decimal("10000.00"),
            unidad_medida="UNID",
            usuario=self.usuario,
            origen="prueba.sql",
        )
        consumo = ConsumoInventario.objects.create(
            cliente=self.cliente,
            ubicacion_origen=self.bodega,
            creado_por=self.usuario,
        )
        DetalleConsumoInventario.objects.create(
            consumo=consumo,
            producto=self.producto,
            cantidad=Decimal("2.00"),
        )

        confirmar_consumo(consumo.pk, self.usuario)

        saldo = ExistenciaInventario.objects.get(
            producto=self.producto,
            ubicacion=self.bodega,
        )
        movimiento = MovimientoInventario.objects.get(tipo="CONSUMO")
        self.assertEqual(saldo.cantidad, Decimal("3.00"))
        self.assertEqual(movimiento.cliente, self.cliente)
        self.assertEqual(movimiento.precio_referencia_snapshot, Decimal("10000.00"))

    def test_consumo_no_permite_stock_negativo(self):
        consumo = ConsumoInventario.objects.create(
            cliente=self.cliente,
            ubicacion_origen=self.bodega,
            creado_por=self.usuario,
        )
        DetalleConsumoInventario.objects.create(
            consumo=consumo,
            producto=self.producto,
            cantidad=Decimal("1.00"),
        )
        with self.assertRaises(ValidationError):
            confirmar_consumo(consumo.pk, self.usuario)
        consumo.refresh_from_db()
        self.assertEqual(consumo.estado, "BORRADOR")


class ReporteConsumosTest(InventarioBaseTest):
    def test_excel_contiene_unidad_codigo_cantidad_y_valores(self):
        MovimientoInventario.objects.create(
            producto=self.producto,
            tipo="CONSUMO",
            cantidad=Decimal("2.00"),
            origen=self.bodega,
            cliente=self.cliente,
            precio_referencia_snapshot=Decimal("12500.00"),
            registrado_por=self.usuario,
        )
        self.client.force_login(self.usuario)

        respuesta = self.client.get(reverse("inventario:exportar_consumos"))

        self.assertEqual(respuesta.status_code, 200)
        libro = load_workbook(BytesIO(respuesta.content), data_only=True)
        hoja = libro["Consumos"]
        self.assertEqual(
            [celda.value for celda in hoja[1]],
            [
                "Fecha",
                "Unidad / cliente",
                "Código",
                "Descripción",
                "Cantidad",
                "Valor unitario",
                "Valor total",
            ],
        )
        self.assertEqual(hoja["B2"].value, "UNIDAD PRUEBA")
        self.assertEqual(hoja["C2"].value, "A001")
        self.assertEqual(hoja["E2"].value, 2)
        self.assertEqual(hoja["F2"].value, 12500)
        self.assertEqual(hoja["G2"].value, 25000)
        self.assertEqual(hoja["G3"].value, 25000)

    def test_usuario_sin_grupo_no_puede_descargar(self):
        otro = User.objects.create_user("sin_permiso", password="segura")
        self.client.force_login(otro)
        respuesta = self.client.get(reverse("inventario:exportar_consumos"))
        self.assertEqual(respuesta.status_code, 403)


class FormulariosInventarioTest(InventarioBaseTest):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.usuario)

    def test_puede_crear_proveedor_desde_inventario(self):
        respuesta = self.client.post(
            reverse("inventario:nuevo_proveedor"),
            {"nombre": "NUEVO PROVEEDOR", "activo": "on"},
        )
        self.assertRedirects(respuesta, reverse("inventario:nueva_entrada"))
        self.assertTrue(Proveedor.objects.filter(nombre="NUEVO PROVEEDOR").exists())

    def test_sugiere_codigo_y_bloquea_codigo_existente(self):
        respuesta = self.client.get(
            reverse("inventario:verificar_codigo_producto"),
            {"prefijo": "A", "codigo": "A001"},
        )
        datos = respuesta.json()
        self.assertFalse(datos["disponible"])
        self.assertEqual(datos["sugerido"], "A002")
        self.assertIn("UNIÓN DE PRUEBA", datos["mensaje"])

    def test_crea_accesorio_y_producto_con_referencia_del_proveedor(self):
        proveedor = Proveedor.objects.create(nombre="PROVEEDOR NUEVO")
        respuesta = self.client.post(
            reverse("inventario:nuevo_producto"),
            {
                "prefijo": "A",
                "codigo": "A002",
                "descripcion": "VÁLVULA NUEVA",
                "unidad_medida": "UNID",
                "stock_minimo": "2.00",
                "precio_referencia": "36120.00",
                "proveedor": proveedor.pk,
                "codigo_proveedor": "REF-99",
                "descripcion_proveedor": "Válvula según factura",
            },
        )
        self.assertRedirects(respuesta, reverse("inventario:nueva_entrada"))
        producto = ProductoInventario.objects.get(accesorio__codigo="A002")
        self.assertEqual(producto.accesorio.descripcion, "VÁLVULA NUEVA")
        self.assertEqual(producto.precio_referencia, Decimal("36120.00"))
        self.assertTrue(
            producto.referencias_proveedor.filter(
                proveedor=proveedor,
                codigo_proveedor="REF-99",
            ).exists()
        )

    def test_no_crea_producto_con_codigo_duplicado(self):
        respuesta = self.client.post(
            reverse("inventario:nuevo_producto"),
            {
                "prefijo": "A",
                "codigo": "A001",
                "descripcion": "OTRO PRODUCTO",
                "unidad_medida": "UNID",
                "stock_minimo": "0.00",
                "precio_referencia": "100.00",
            },
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "ya pertenece a UNIÓN DE PRUEBA")
        self.assertFalse(Accesorio.objects.filter(descripcion="OTRO PRODUCTO").exists())

    def test_no_crea_producto_con_descripcion_duplicada(self):
        respuesta = self.client.post(
            reverse("inventario:nuevo_producto"),
            {
                "prefijo": "A",
                "codigo": "A002",
                "descripcion": "unión de prueba",
                "unidad_medida": "UNID",
                "stock_minimo": "0.00",
                "precio_referencia": "100.00",
            },
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "ya existe con el código A001")
        self.assertFalse(Accesorio.objects.filter(codigo="A002").exists())

    def test_entrada_acepta_referencia_del_proveedor_y_producto(self):
        proveedor = Proveedor.objects.create(nombre="PROVEEDOR REFERENCIA")
        referencia = ReferenciaProveedor.objects.create(
            producto=self.producto,
            proveedor=proveedor,
            codigo_proveedor="REF-A001",
        )
        respuesta = self.client.post(
            reverse("inventario:nueva_entrada"),
            {
                "proveedor": proveedor.pk,
                "numero_factura": "FV-REFERENCIA",
                "fecha_factura": "2026-10-06",
                "observaciones": "Prueba",
                "detalles-TOTAL_FORMS": "1",
                "detalles-INITIAL_FORMS": "0",
                "detalles-MIN_NUM_FORMS": "0",
                "detalles-MAX_NUM_FORMS": "1000",
                "detalles-0-producto": self.producto.pk,
                "detalles-0-referencia_proveedor": referencia.pk,
                "detalles-0-cantidad": "2.00",
                "detalles-0-precio_unitario_lista": "12000.00",
                "detalles-0-porcentaje_descuento": "10.00",
            },
        )
        self.assertRedirects(respuesta, reverse("inventario:tablero"))
        detalle = DetalleEntradaInventario.objects.get(
            entrada__numero_factura="FV-REFERENCIA"
        )
        self.assertEqual(detalle.referencia_proveedor, referencia)

    def test_entrada_acepta_producto_sin_referencia_del_proveedor(self):
        proveedor = Proveedor.objects.create(nombre="PROVEEDOR SIN REFERENCIA")
        respuesta = self.client.post(
            reverse("inventario:nueva_entrada"),
            {
                "proveedor": proveedor.pk,
                "numero_factura": "FV-SIN-REFERENCIA",
                "fecha_factura": "2026-10-09",
                "detalles-TOTAL_FORMS": "1",
                "detalles-INITIAL_FORMS": "0",
                "detalles-MIN_NUM_FORMS": "0",
                "detalles-MAX_NUM_FORMS": "1000",
                "detalles-0-producto": self.producto.pk,
                "detalles-0-referencia_proveedor": "",
                "detalles-0-cantidad": "1.00",
                "detalles-0-precio_unitario_lista": "100.00",
                "detalles-0-porcentaje_descuento": "0.00",
            },
        )
        self.assertRedirects(respuesta, reverse("inventario:tablero"))
        detalle = DetalleEntradaInventario.objects.get(
            entrada__numero_factura="FV-SIN-REFERENCIA"
        )
        self.assertIsNone(detalle.referencia_proveedor)

    def test_entrada_entrega_referencias_para_filtrar_por_producto_y_proveedor(self):
        proveedor = Proveedor.objects.create(nombre="PROVEEDOR FILTRO")
        referencia = ReferenciaProveedor.objects.create(
            producto=self.producto,
            proveedor=proveedor,
            codigo_proveedor="REF-A001",
            descripcion_proveedor="Referencia de prueba",
        )
        respuesta = self.client.get(reverse("inventario:nueva_entrada"))

        self.assertEqual(
            respuesta.context["referencias_disponibles"],
            [
                {
                    "id": referencia.pk,
                    "producto_id": self.producto.pk,
                    "proveedor_id": proveedor.pk,
                    "etiqueta": "REF-A001 — Referencia de prueba",
                }
            ],
        )
        self.assertContains(respuesta, "referencias-proveedor-data")
        self.assertContains(respuesta, "Sin referencia del proveedor (opcional)")

    def test_entrada_muestra_error_si_referencia_no_corresponde(self):
        proveedor = Proveedor.objects.create(nombre="PROVEEDOR FACTURA")
        otro = Proveedor.objects.create(nombre="OTRO PROVEEDOR")
        referencia = ReferenciaProveedor.objects.create(
            producto=self.producto,
            proveedor=otro,
            codigo_proveedor="REF-OTRA",
        )
        respuesta = self.client.post(
            reverse("inventario:nueva_entrada"),
            {
                "proveedor": proveedor.pk,
                "numero_factura": "FV-INVALIDA",
                "fecha_factura": "2026-10-06",
                "detalles-TOTAL_FORMS": "1",
                "detalles-INITIAL_FORMS": "0",
                "detalles-MIN_NUM_FORMS": "0",
                "detalles-MAX_NUM_FORMS": "1000",
                "detalles-0-producto": self.producto.pk,
                "detalles-0-referencia_proveedor": referencia.pk,
                "detalles-0-cantidad": "1.00",
                "detalles-0-precio_unitario_lista": "100.00",
                "detalles-0-porcentaje_descuento": "0.00",
            },
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(
            respuesta,
            "La referencia no corresponde al proveedor y producto seleccionados.",
        )
        self.assertFalse(
            EntradaInventario.objects.filter(numero_factura="FV-INVALIDA").exists()
        )

    def test_edita_descripcion_sin_cambiar_codigo_ni_historial(self):
        movimiento = MovimientoInventario.objects.create(
            producto=self.producto,
            tipo="SALDO_INICIAL",
            cantidad=Decimal("1.00"),
            destino=self.bodega,
            registrado_por=self.usuario,
        )
        accesorio_id = self.producto.accesorio_id
        respuesta = self.client.post(
            reverse("inventario:editar_producto", args=[self.producto.pk]),
            {
                "descripcion": "UNIÓN ACTUALIZADA",
                "unidad_medida": "pieza",
                "stock_minimo": "3.00",
            },
        )
        self.assertRedirects(respuesta, reverse("inventario:tablero"))
        self.producto.refresh_from_db()
        self.producto.accesorio.refresh_from_db()
        movimiento.refresh_from_db()
        self.assertEqual(self.producto.accesorio_id, accesorio_id)
        self.assertEqual(self.producto.accesorio.codigo, "A001")
        self.assertEqual(self.producto.accesorio.descripcion, "UNIÓN ACTUALIZADA")
        self.assertEqual(self.producto.unidad_medida, "PIEZA")
        self.assertEqual(self.producto.stock_minimo, Decimal("3.00"))
        self.assertEqual(movimiento.producto, self.producto)

    def test_lista_accesorios_incluye_productos_sin_existencia(self):
        respuesta = self.client.get(reverse("inventario:lista_productos"))
        self.assertContains(respuesta, "A001")
        self.assertContains(respuesta, "Editar")

    def test_entrada_muestra_boton_crear_accesorio(self):
        respuesta = self.client.get(reverse("inventario:nueva_entrada"))
        self.assertContains(respuesta, "+ Crear accesorio")

    def test_consumo_ofrece_busqueda_y_filas_dinamicas(self):
        respuesta = self.client.get(reverse("inventario:nuevo_consumo"))
        self.assertContains(respuesta, "Buscar unidad / cliente")
        self.assertContains(respuesta, "lista-clientes")
        self.assertContains(respuesta, "resultados-clientes")
        self.assertContains(respuesta, "No se encontraron unidades")
        self.assertContains(respuesta, "UNIDAD PRUEBA")
        self.assertContains(respuesta, "logo_dys.png")
        self.assertContains(respuesta, "lista-productos")
        self.assertContains(respuesta, "A001")
        self.assertContains(respuesta, "+ Agregar otro accesorio")
        self.assertContains(respuesta, "fila-vacia")
        self.assertContains(respuesta, "Confirmar y registrar otra unidad")
        self.assertContains(respuesta, "Confirmar y terminar")

    def test_confirma_consumo_y_deja_formulario_para_otra_unidad(self):
        fijar_saldo_inicial(
            producto=self.producto,
            cantidad=Decimal("5.00"),
            precio_referencia=Decimal("10000.00"),
            unidad_medida="UNID",
            usuario=self.usuario,
            origen="consumo-consecutivo.sql",
        )
        respuesta = self.client.post(
            reverse("inventario:nuevo_consumo"),
            {
                "cliente": self.cliente.pk,
                "ubicacion_origen": self.bodega.pk,
                "fecha": "2026-10-06T14:00",
                "observaciones": "Consumo consecutivo",
                "accion": "confirmar_continuar",
                "detalles-TOTAL_FORMS": "1",
                "detalles-INITIAL_FORMS": "0",
                "detalles-MIN_NUM_FORMS": "0",
                "detalles-MAX_NUM_FORMS": "1000",
                "detalles-0-producto": self.producto.pk,
                "detalles-0-cantidad": "2.00",
            },
        )
        self.assertRedirects(respuesta, reverse("inventario:nuevo_consumo"))
        consumo = ConsumoInventario.objects.get()
        self.assertEqual(consumo.estado, "CONFIRMADO")
        saldo = ExistenciaInventario.objects.get(
            producto=self.producto,
            ubicacion=self.bodega,
        )
        self.assertEqual(saldo.cantidad, Decimal("3.00"))

    def test_tablero_muestra_accion_de_ajuste_y_estadisticas(self):
        fijar_saldo_inicial(
            producto=self.producto,
            cantidad=Decimal("5.00"),
            precio_referencia=Decimal("10000.00"),
            unidad_medida="UNID",
            usuario=self.usuario,
            origen="tablero.sql",
        )
        respuesta = self.client.get(reverse("inventario:tablero"))
        self.assertContains(respuesta, "Ajustar existencia")
        self.assertContains(respuesta, "Accesorios más utilizados")
        self.assertContains(respuesta, "Unidades con mayor consumo")


class AjusteExistenciaTest(InventarioBaseTest):
    def setUp(self):
        super().setUp()
        fijar_saldo_inicial(
            producto=self.producto,
            cantidad=Decimal("5.00"),
            precio_referencia=Decimal("10000.00"),
            unidad_medida="UNID",
            usuario=self.usuario,
            origen="ajustes.sql",
        )
        self.existencia = ExistenciaInventario.objects.get(
            producto=self.producto,
            ubicacion=self.bodega,
        )

    def test_ajuste_entrada_conserva_trazabilidad(self):
        movimiento = ajustar_existencia(
            existencia_id=self.existencia.pk,
            cantidad_fisica=Decimal("8.00"),
            motivo="Conteo físico de inventario",
            observaciones="Se realizó conteo en bodega.",
            usuario=self.usuario,
        )
        self.existencia.refresh_from_db()
        self.assertEqual(self.existencia.cantidad, Decimal("8.00"))
        self.assertEqual(movimiento.tipo, "AJUSTE_ENTRADA")
        self.assertEqual(movimiento.cantidad, Decimal("3.00"))
        self.assertEqual(movimiento.registrado_por, self.usuario)
        self.assertIn("Saldo anterior: 5.00", movimiento.observaciones)

    def test_ajuste_salida_desde_vista(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.post(
            reverse("inventario:ajustar_existencia", args=[self.existencia.pk]),
            {
                "cantidad_fisica": "2.00",
                "motivo": "PERDIDA",
                "observaciones": "Faltante confirmado durante conteo.",
            },
        )
        self.assertRedirects(respuesta, reverse("inventario:tablero"))
        self.existencia.refresh_from_db()
        self.assertEqual(self.existencia.cantidad, Decimal("2.00"))
        movimiento = MovimientoInventario.objects.get(tipo="AJUSTE_SALIDA")
        self.assertEqual(movimiento.cantidad, Decimal("3.00"))

    def test_no_permite_ajuste_sin_diferencia(self):
        with self.assertRaises(ValidationError):
            ajustar_existencia(
                existencia_id=self.existencia.pk,
                cantidad_fisica=Decimal("5.00"),
                motivo="Conteo físico de inventario",
                observaciones="Sin diferencia.",
                usuario=self.usuario,
            )


class IntegracionOperacionTest(InventarioBaseTest):
    def test_remision_consumo_y_devolucion_conservan_trazabilidad(self):
        tecnico = Tecnico.objects.create(
            nombre="Técnico inventario",
            telefono="3000000000",
            especialidad="Bombas",
            valor_hora_diurna=Decimal("1.00"),
            valor_hora_nocturna=Decimal("1.00"),
        )
        fijar_saldo_inicial(
            producto=self.producto,
            cantidad=Decimal("10.00"),
            precio_referencia=Decimal("10000.00"),
            unidad_medida="UNID",
            usuario=self.usuario,
            origen="integracion.sql",
        )
        remision = RemisionTecnico.objects.create(
            numero_remision="REM-INVENTARIO-1",
            tecnico=tecnico,
            cliente=self.cliente,
            entregado_por=self.usuario,
        )
        detalle = DetalleRemision.objects.create(
            remision=remision,
            accesorio=self.producto.accesorio,
            cantidad_entregada=Decimal("4.00"),
        )

        registrar_entrega_remision(remision, self.usuario)
        ubicacion_tecnico = obtener_ubicacion_tecnico(tecnico)
        self.assertEqual(
            ExistenciaInventario.objects.get(
                producto=self.producto,
                ubicacion=self.bodega,
            ).cantidad,
            Decimal("6.00"),
        )
        self.assertEqual(
            ExistenciaInventario.objects.get(
                producto=self.producto,
                ubicacion=ubicacion_tecnico,
            ).cantidad,
            Decimal("4.00"),
        )

        actividad = ActividadTecnico.objects.create(
            tecnico=tecnico,
            cliente=self.cliente,
            remision=remision,
            labor_realizada="Instalación de accesorio",
            registrado_por=self.usuario,
        )
        uso = AccesorioActividad.objects.create(
            actividad=actividad,
            accesorio=self.producto.accesorio,
            detalle_remision=detalle,
            cantidad=Decimal("3.00"),
        )
        registrar_consumo_actividad(uso, self.usuario)
        detalle.actualizar_utilizado_desde_informes()
        detalle.cantidad_devuelta = Decimal("1.00")
        detalle.save(update_fields=["cantidad_devuelta"])
        registrar_devolucion_detalle(detalle, self.usuario)

        self.assertEqual(
            ExistenciaInventario.objects.get(
                producto=self.producto,
                ubicacion=ubicacion_tecnico,
            ).cantidad,
            Decimal("0.00"),
        )
        self.assertEqual(
            ExistenciaInventario.objects.get(
                producto=self.producto,
                ubicacion=self.bodega,
            ).cantidad,
            Decimal("7.00"),
        )
        consumo = MovimientoInventario.objects.get(tipo="CONSUMO")
        self.assertEqual(consumo.cliente, self.cliente)
        self.assertEqual(consumo.cantidad, Decimal("3.00"))
