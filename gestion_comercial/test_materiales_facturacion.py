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

from .models import CatalogoPrecio, RevisionMaterialUtilizado


class MaterialesFacturacionTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.cliente_unidad = Cliente.objects.create(
            nombre="Unidad comercial de prueba",
            direccion="Calle 1",
            telefono_porteria="123",
            administrador="Administración",
            email="unidad@example.com",
            tipo_contrato="PREVENTIVO",
            frecuencia_lavado=6,
        )
        cls.usuario_tecnico = User.objects.create_user(
            "tecnico_materiales",
            password="clave",
        )
        cls.tecnico = Tecnico.objects.create(
            user=cls.usuario_tecnico,
            nombre="Técnico materiales",
            telefono="3000000000",
            especialidad="Bombas",
            valor_hora_diurna=1,
            valor_hora_nocturna=1,
        )
        cls.actividad = ActividadTecnico.objects.create(
            tecnico=cls.tecnico,
            cliente=cls.cliente_unidad,
            labor_realizada="Cambio de accesorio",
        )
        cls.accesorio = Accesorio.objects.create(
            codigo="MAT-001",
            descripcion="Material con precio",
        )
        cls.consumo = AccesorioActividad.objects.create(
            actividad=cls.actividad,
            accesorio=cls.accesorio,
            cantidad=Decimal("2.00"),
        )
        cls.catalogo = CatalogoPrecio.objects.create(
            codigo="MAT-001",
            descripcion="Material comercial con precio",
            valor=Decimal("12500.00"),
        )

        cls.facturacion = User.objects.create_user(
            "facturacion_materiales",
            password="clave",
            is_staff=True,
        )
        cls.facturacion.groups.add(
            Group.objects.get_or_create(name="GESTION_FACTURACION")[0]
        )
        cls.gerencia = User.objects.create_user(
            "gerencia_materiales",
            password="clave",
            is_staff=True,
        )
        cls.gerencia.groups.add(
            Group.objects.get_or_create(name="GESTION_GERENCIA")[0]
        )
        cls.sin_rol = User.objects.create_user(
            "sin_rol_materiales",
            password="clave",
            is_staff=True,
        )

    def test_lista_exige_autenticacion(self):
        respuesta = self.client.get(
            reverse("gestion_comercial:lista_materiales_utilizados")
        )
        self.assertEqual(respuesta.status_code, 302)

    def test_usuario_sin_rol_no_puede_consultar(self):
        self.client.force_login(self.sin_rol)
        respuesta = self.client.get(
            reverse("gestion_comercial:lista_materiales_utilizados")
        )
        self.assertEqual(respuesta.status_code, 403)

    def test_gerencia_puede_consultar_pero_no_clasificar(self):
        self.client.force_login(self.gerencia)
        lista = self.client.get(
            reverse("gestion_comercial:lista_materiales_utilizados")
        )
        self.assertEqual(lista.status_code, 200)

        clasificacion = self.client.post(
            reverse(
                "gestion_comercial:clasificar_material_utilizado",
                args=[self.consumo.pk],
            ),
            {"estado": "FACTURAR"},
        )
        self.assertEqual(clasificacion.status_code, 403)

    def test_facturacion_clasifica_y_conserva_snapshot(self):
        self.client.force_login(self.facturacion)
        respuesta = self.client.post(
            reverse(
                "gestion_comercial:clasificar_material_utilizado",
                args=[self.consumo.pk],
            ),
            {
                "estado": "FACTURAR",
                "observaciones": "Cobrar al cliente",
            },
        )
        self.assertEqual(respuesta.status_code, 302)

        revision = RevisionMaterialUtilizado.objects.get(
            consumo=self.consumo
        )
        self.assertEqual(revision.estado, "FACTURAR")
        self.assertEqual(revision.catalogo_precio, self.catalogo)
        self.assertEqual(revision.codigo_snapshot, "MAT-001")
        self.assertEqual(revision.descripcion_snapshot, "Material con precio")
        self.assertEqual(revision.cantidad_snapshot, Decimal("2.00"))
        self.assertEqual(
            revision.valor_unitario_sugerido,
            Decimal("12500.00"),
        )
        self.assertEqual(revision.revisado_por, self.facturacion)

    def test_no_permite_facturar_material_sin_precio(self):
        accesorio = Accesorio.objects.create(
            codigo="SIN-PRECIO",
            descripcion="Material sin precio",
        )
        consumo = AccesorioActividad.objects.create(
            actividad=self.actividad,
            accesorio=accesorio,
            cantidad=Decimal("1.00"),
        )
        self.client.force_login(self.facturacion)
        respuesta = self.client.post(
            reverse(
                "gestion_comercial:clasificar_material_utilizado",
                args=[consumo.pk],
            ),
            {"estado": "FACTURAR"},
        )
        self.assertEqual(respuesta.status_code, 302)
        self.assertFalse(
            RevisionMaterialUtilizado.objects.filter(consumo=consumo).exists()
        )

    def test_sin_precio_admite_clasificacion_no_facturable(self):
        accesorio = Accesorio.objects.create(
            codigo="GARANTIA-1",
            descripcion="Material de garantía",
        )
        consumo = AccesorioActividad.objects.create(
            actividad=self.actividad,
            accesorio=accesorio,
            cantidad=Decimal("1.00"),
        )
        self.client.force_login(self.facturacion)
        respuesta = self.client.post(
            reverse(
                "gestion_comercial:clasificar_material_utilizado",
                args=[consumo.pk],
            ),
            {"estado": "GARANTIA"},
        )
        self.assertEqual(respuesta.status_code, 302)
        revision = RevisionMaterialUtilizado.objects.get(consumo=consumo)
        self.assertEqual(revision.estado, "GARANTIA")
        self.assertIsNone(revision.valor_unitario_sugerido)

    def test_clasificacion_rechaza_get(self):
        self.client.force_login(self.facturacion)
        respuesta = self.client.get(
            reverse(
                "gestion_comercial:clasificar_material_utilizado",
                args=[self.consumo.pk],
            )
        )
        self.assertEqual(respuesta.status_code, 405)
