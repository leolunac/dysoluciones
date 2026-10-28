import json
from unittest.mock import patch, MagicMock
from django.test import SimpleTestCase, override_settings
from .whatsapp_plantilla_prueba import construir_payload, enviar_prueba_plantilla, ErrorPruebaWhatsApp

SQLITE = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
ENV = {'SIGOB_WHATSAPP_PRUEBA': '1', 'SIGOB_WHATSAPP_TOKEN': 'token-ficticio', 'SIGOB_WHATSAPP_TELEFONO_ID': '123', 'SIGOB_WHATSAPP_DESTINO_PRUEBA': '573000000000'}

class PlantillaPruebaTests(SimpleTestCase):
    def test_orden_de_variables(self):
        p = construir_payload('Carlos', 'preventivo', 'Unidad de prueba', '30/10/2026', '573000000000')
        self.assertEqual(p['template']['name'], 'asignacion_mantenimiento')
        self.assertEqual(p['template']['language']['code'], 'es')
        self.assertEqual([v['text'] for v in p['template']['components'][0]['parameters']], ['Carlos', 'preventivo', 'Unidad de prueba', '30/10/2026'])

    def test_no_acepta_destino_invalido(self):
        with self.assertRaises(ErrorPruebaWhatsApp):
            construir_payload('Carlos', 'preventivo', 'Unidad', '30/10/2026', '+573000000000')

    @override_settings(DEBUG=False, DATABASES=SQLITE)
    @patch.dict('os.environ', ENV, clear=True)
    @patch('operacion.whatsapp_plantilla_prueba.urlopen')
    def test_bloqueo_fuera_de_desarrollo(self, abrir):
        with self.assertRaises(ErrorPruebaWhatsApp):
            enviar_prueba_plantilla('Carlos', 'preventivo', 'Unidad', '30/10/2026')
        abrir.assert_not_called()

    @override_settings(DEBUG=True, DATABASES=SQLITE)
    @patch.dict('os.environ', ENV, clear=True)
    @patch('operacion.whatsapp_plantilla_prueba.urlopen')
    def test_envia_solo_al_destino_configurado(self, abrir):
        respuesta = MagicMock()
        respuesta.read.return_value = b'{"messages":[{"id":"prueba"}]}'
        abrir.return_value.__enter__.return_value = respuesta
        resultado = enviar_prueba_plantilla('Carlos', 'preventivo', 'Unidad', '30/10/2026')
        solicitud = abrir.call_args.args[0]
        self.assertEqual(json.loads(solicitud.data)['to'], ENV['SIGOB_WHATSAPP_DESTINO_PRUEBA'])
        self.assertIn('Meta aceptó', resultado)
