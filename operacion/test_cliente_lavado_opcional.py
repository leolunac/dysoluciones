from datetime import date
from django.forms import modelform_factory
from django.test import TestCase
from .models import Cliente


class ClienteLavadoOpcionalTests(TestCase):
    def datos(self, **cambios):
        datos = dict(nombre="Unidad de prueba", direccion="Calle 1", telefono_porteria="6040000000",
                     administrador="Administración", email="prueba@example.com", tipo_contrato="SIN_CONTRATO")
        datos.update(cambios)
        return datos

    def test_formulario_guarda_sin_lavado(self):
        formulario = modelform_factory(Cliente, fields=["nombre", "direccion", "telefono_porteria",
            "administrador", "email", "tipo_contrato", "frecuencia_lavado", "fecha_ultimo_lavado"])
        form = formulario(data=self.datos(frecuencia_lavado="", fecha_ultimo_lavado=""))
        self.assertTrue(form.is_valid(), form.errors)
        cliente = form.save()
        cliente.refresh_from_db()
        self.assertIsNone(cliente.frecuencia_lavado)
        self.assertEqual(cliente.get_frecuencia_lavado_display(), "Sin lavado periódico")

    def test_periodicidades_existentes_se_conservan(self):
        for meses in (4, 6):
            cliente = Cliente.objects.create(**self.datos(frecuencia_lavado=meses))
            cliente.refresh_from_db()
            self.assertEqual(cliente.frecuencia_lavado, meses)

    def test_sin_contrato_puede_tener_lavado_periodico(self):
        cliente = Cliente(**self.datos(frecuencia_lavado=4))
        cliente.full_clean()

    def test_quitar_periodicidad_conserva_fecha_historica(self):
        cliente = Cliente.objects.create(**self.datos(frecuencia_lavado=6, fecha_ultimo_lavado=date(2026, 1, 2)))
        cliente.frecuencia_lavado = None
        cliente.save()
        cliente.refresh_from_db()
        self.assertEqual(cliente.fecha_ultimo_lavado, date(2026, 1, 2))

    def test_frecuencia_invalida_rechazada(self):
        formulario = modelform_factory(Cliente, fields=["frecuencia_lavado"])
        self.assertFalse(formulario(data={"frecuencia_lavado": 3}).is_valid())
