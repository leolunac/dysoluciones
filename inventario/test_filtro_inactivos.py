from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from openpyxl import load_workbook

from operacion.models import Accesorio
from .models import ExistenciaInventario, MovimientoInventario, ProductoInventario, UbicacionInventario
from . import views


class FiltroInactivosTest(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser(
            username="revision_inactivos", email="revision@example.com", password="prueba"
        )
        self.factory = RequestFactory()
        self.bodega = UbicacionInventario.objects.create(nombre="Bodega prueba filtros", tipo="BODEGA")
        self.activo = self.producto("A190", True, True, "5", "6")
        self.agotado = self.producto("A191", True, True, "0", "1")
        self.inactivo = self.producto("E398", False, True, "2", "10")
        self.accesorio_inactivo = self.producto("E399", True, False, "3", "10")

    def producto(self, codigo, activo, accesorio_activo, cantidad, minimo):
        accesorio = Accesorio.objects.create(
            codigo=codigo, descripcion="Producto " + codigo, activo=accesorio_activo
        )
        producto = ProductoInventario.objects.create(
            accesorio=accesorio, activo=activo, stock_minimo=Decimal(minimo),
            precio_referencia=Decimal("14730")
        )
        ExistenciaInventario.objects.create(
            producto=producto, ubicacion=self.bodega, cantidad=Decimal(cantidad)
        )
        return producto

    def request(self, datos=None):
        request = self.factory.get("/inventario/", datos or {})
        request.user = self.usuario
        return request

    def tablero(self, datos=None):
        with patch("inventario.views.render", return_value=HttpResponse()) as render:
            views.tablero(self.request(datos))
        return render.call_args.args[2]

    def test_listado_conserva_activos_incluso_agotados(self):
        contexto = self.tablero()
        self.assertEqual(
            {e.producto_id for e in contexto["existencias"]},
            {self.activo.pk, self.agotado.pk},
        )

    def test_busqueda_no_reintroduce_producto_o_accesorio_inactivo(self):
        for codigo in ("E398", "E399"):
            with self.subTest(codigo=codigo):
                contexto = self.tablero({"buscar": codigo})
                self.assertEqual(contexto["pagina"].paginator.count, 0)
        contexto = self.tablero({"buscar": "a190"})
        self.assertEqual(contexto["pagina"].paginator.count, 1)

    def test_resumen_y_minimos_excluyen_ambas_clases_de_inactivos(self):
        contexto = self.tablero({"buscar": "E398"})
        self.assertEqual(contexto["total_unidades"], Decimal("5"))
        self.assertEqual(contexto["valor_inventario"], Decimal("73650"))
        self.assertEqual(contexto["productos_bajo_minimo"], 2)

    def test_excel_existencias_coincide_con_listado_y_totales(self):
        respuesta = views.exportar_existencias_excel(self.request())
        libro = load_workbook(BytesIO(respuesta.content))
        filas = list(libro["Existencias"].values)
        self.assertEqual({fila[0] for fila in filas[1:-1]}, {"A190", "A191"})
        self.assertEqual(filas[-1][4], 5)
        self.assertEqual(filas[-1][7], 73650)
        libro.close()

    def test_reporte_consumos_conserva_historial_de_inactivos(self):
        movimiento = MovimientoInventario.objects.create(
            producto=self.inactivo, tipo="CONSUMO", cantidad=Decimal("1"),
            origen=self.bodega, registrado_por=self.usuario,
            precio_referencia_snapshot=Decimal("14730"), referencia="Consumo anterior"
        )
        respuesta = views.exportar_consumos_excel(self.request())
        libro = load_workbook(BytesIO(respuesta.content))
        for nombre in ("Consumos", "Movimientos"):
            self.assertIn("E398", {fila[2] for fila in list(libro[nombre].values)[1:-1]})
        self.assertTrue(MovimientoInventario.objects.filter(pk=movimiento.pk).exists())
        self.assertEqual(ExistenciaInventario.objects.get(producto=self.inactivo).cantidad, Decimal("2"))
        libro.close()
