import json
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from .ia_redaccion import ErrorRevisionIA, revisar_redaccion
from .models import Tecnico


class ServicioRedaccionIATests(TestCase):
    @override_settings(OPENAI_API_KEY="clave-prueba", OPENAI_MODEL="modelo-prueba")
    @patch("operacion.ia_redaccion.requests.post")
    def test_corrige_sin_almacenar_y_con_esquema_estricto(self, post):
        post.return_value = Mock(
            status_code=200,
            json=lambda: {
                "output": [{"content": [{
                    "type": "output_text",
                    "text": json.dumps({"diagnostico": "Se revisó la bomba."}),
                }]}]
            },
        )

        resultado = revisar_redaccion({"diagnostico": "se reviso la bomba"})

        self.assertEqual(resultado["diagnostico"], "Se revisó la bomba.")
        datos = post.call_args.kwargs["json"]
        self.assertFalse(datos["store"])
        self.assertEqual(datos["max_output_tokens"], 1800)
        self.assertTrue(datos["text"]["format"]["strict"])
        self.assertIn("No inventes", datos["instructions"])

    @override_settings(OPENAI_API_KEY="")
    def test_sin_clave_informa_que_no_esta_configurada(self):
        with self.assertRaisesMessage(ErrorRevisionIA, "todavía no está configurada"):
            revisar_redaccion({"diagnostico": "Texto"})


class VistaRedaccionIATests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = User.objects.create_user("tecnico_ia", password="clave")
        Tecnico.objects.create(
            user=cls.usuario,
            nombre="Técnico IA",
            telefono="3000000000",
            especialidad="Bombas",
            valor_hora_diurna=1,
            valor_hora_nocturna=1,
        )
        cls.otro = User.objects.create_user("sin_permiso_ia", password="clave")

    @patch("operacion.views.revisar_redaccion")
    def test_tecnico_recibe_propuesta_sin_guardar_informe(self, revisar):
        revisar.return_value = {"diagnostico": "Se revisó la bomba."}
        self.client.force_login(self.usuario)
        respuesta = self.client.post(
            reverse("revisar_redaccion_ia"),
            data=json.dumps({
                "contexto": "correctivo",
                "campos": {"diagnostico": "se reviso la bomba"},
            }),
            content_type="application/json",
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()["campos"]["diagnostico"], "Se revisó la bomba.")

    def test_usuario_sin_permiso_es_rechazado(self):
        self.client.force_login(self.otro)
        respuesta = self.client.post(
            reverse("revisar_redaccion_ia"),
            data=json.dumps({"campos": {"texto": "Prueba"}}),
            content_type="application/json",
        )
        self.assertEqual(respuesta.status_code, 403)

    @patch("operacion.views.revisar_redaccion")
    def test_error_del_servicio_se_muestra_sin_error_500(self, revisar):
        revisar.side_effect = ErrorRevisionIA("Servicio temporalmente no disponible.")
        self.client.force_login(self.usuario)
        respuesta = self.client.post(
            reverse("revisar_redaccion_ia"),
            data=json.dumps({"campos": {"texto": "Prueba"}}),
            content_type="application/json",
        )
        self.assertEqual(respuesta.status_code, 503)
        self.assertFalse(respuesta.json()["ok"])
