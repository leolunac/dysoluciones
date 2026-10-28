from datetime import date
from types import SimpleNamespace
from unittest.mock import patch
from django.test import SimpleTestCase, override_settings
from .whatsapp_asignacion_prueba import programar_preventivo_prueba, programar_correctivo_prueba

SQLITE = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}

@override_settings(DEBUG=True, DATABASES=SQLITE)
class AsignacionWhatsAppTests(SimpleTestCase):
    def registro(self, **extras):
        valores = dict(tecnico_id=1, tecnico=SimpleNamespace(nombre='Tecnico de prueba'), cliente=SimpleNamespace(nombre='Unidad ficticia'), fecha_programada=date(2026, 11, 3), tipo_servicio='CORRECTIVO')
        valores.update(extras)
        return SimpleNamespace(**valores)

    @patch.dict('os.environ', {'SIGOB_WHATSAPP_PRUEBA': '1'}, clear=True)
    @patch('operacion.whatsapp_asignacion_prueba.enviar_prueba_plantilla')
    @patch('operacion.whatsapp_asignacion_prueba.transaction.on_commit')
    def test_preventivo_envia_fecha_programada_despues_del_commit(self, commit, enviar):
        programar_preventivo_prueba(self.registro())
        enviar.assert_not_called()
        commit.call_args.args[0]()
        enviar.assert_called_once_with('Tecnico de prueba', 'preventivo', 'Unidad ficticia', '03/11/2026')

    @patch.dict('os.environ', {'SIGOB_WHATSAPP_PRUEBA': '1'}, clear=True)
    @patch('operacion.whatsapp_asignacion_prueba.timezone.localdate', return_value=date(2026, 10, 28))
    @patch('operacion.whatsapp_asignacion_prueba.enviar_prueba_plantilla')
    @patch('operacion.whatsapp_asignacion_prueba.transaction.on_commit')
    def test_correctivo_envia_fecha_asignacion(self, commit, enviar, fecha):
        programar_correctivo_prueba(self.registro())
        commit.call_args.args[0]()
        enviar.assert_called_once_with('Tecnico de prueba', 'correctivo', 'Unidad ficticia', '28/10/2026')

    @override_settings(DEBUG=False)
    @patch.dict('os.environ', {'SIGOB_WHATSAPP_PRUEBA': '1'}, clear=True)
    @patch('operacion.whatsapp_asignacion_prueba.transaction.on_commit')
    def test_no_se_habilita_en_produccion(self, commit):
        programar_correctivo_prueba(self.registro())
        programar_preventivo_prueba(self.registro())
        commit.assert_not_called()

    @patch.dict('os.environ', {}, clear=True)
    @patch('operacion.whatsapp_asignacion_prueba.transaction.on_commit')
    def test_no_se_habilita_sin_bandera(self, commit):
        programar_correctivo_prueba(self.registro())
        commit.assert_not_called()

    @patch.dict('os.environ', {'SIGOB_WHATSAPP_PRUEBA': '1'}, clear=True)
    @patch('operacion.whatsapp_asignacion_prueba.transaction.on_commit')
    def test_no_envia_sin_tecnico_o_para_otro_tipo(self, commit):
        programar_correctivo_prueba(self.registro(tecnico_id=None))
        programar_correctivo_prueba(self.registro(tipo_servicio='LAVADO'))
        programar_preventivo_prueba(self.registro(tecnico_id=None))
        commit.assert_not_called()

    @patch.dict('os.environ', {'SIGOB_WHATSAPP_PRUEBA': '1'}, clear=True)
    @patch('operacion.whatsapp_asignacion_prueba.enviar_prueba_plantilla', side_effect=RuntimeError('error ficticio'))
    @patch('operacion.whatsapp_asignacion_prueba.transaction.on_commit')
    def test_falla_del_envio_no_propaga_error(self, commit, enviar):
        programar_correctivo_prueba(self.registro())
        with self.assertLogs('operacion.whatsapp_asignacion_prueba', level='WARNING'):
            commit.call_args.args[0]()
