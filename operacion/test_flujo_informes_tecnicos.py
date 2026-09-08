import shutil
import tempfile
from datetime import date
from pathlib import Path

from django.contrib.auth.models import Group, User
from django.test import TestCase, override_settings
from django.urls import reverse

from portal_cliente.models import DocumentoCliente

from .models import (
    ActividadTecnico,
    Cliente,
    Emergencia,
    MantenimientoPreventivo,
    MedicionEquipoPreventivo,
    ProgramacionMantenimientoPreventivo,
    SectorCliente,
    SeguimientoAnomaliaPreventivo,
    Tecnico,
)


class FlujoInformesTecnicosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.temp_media = Path(tempfile.mkdtemp(prefix="sigob_informes_test_"))
        cls.cliente = Cliente.objects.create(
            nombre="Unidad de prueba",
            direccion="Calle 1",
            telefono_porteria="123",
            administrador="Administración",
            email="cliente@example.com",
            tipo_contrato="PREVENTIVO",
            frecuencia_lavado=6,
        )
        cls.sector = SectorCliente.objects.create(
            cliente=cls.cliente,
            nombre="Torre 1",
        )
        cls.usuario_tecnico = User.objects.create_user("tecnico_informes", password="clave")
        cls.tecnico = Tecnico.objects.create(
            user=cls.usuario_tecnico,
            nombre="Técnico de prueba",
            telefono="3000000000",
            especialidad="Bombas",
            valor_hora_diurna=1,
            valor_hora_nocturna=1,
        )
        cls.otro_usuario = User.objects.create_user("otro_tecnico", password="clave")
        cls.otro_tecnico = Tecnico.objects.create(
            user=cls.otro_usuario,
            nombre="Otro técnico",
            telefono="3000000001",
            especialidad="Bombas",
            valor_hora_diurna=1,
            valor_hora_nocturna=1,
        )
        cls.coordinador = User.objects.create_user(
            "coordinador_informes",
            password="clave",
            is_staff=True,
        )
        cls.coordinador.groups.add(
            Group.objects.get_or_create(name="GESTION_COORDINADOR")[0]
        )
        cls.supervisor = User.objects.create_user(
            "supervisor_informes",
            password="clave",
            is_staff=True,
        )
        cls.supervisor.groups.add(
            Group.objects.get_or_create(name="GESTION_SUPERVISOR")[0]
        )
        cls.sin_rol = User.objects.create_user(
            "interno_sin_rol",
            password="clave",
            is_staff=True,
        )
        cls.coordinador_sin_staff = User.objects.create_user(
            "coordinador_sin_staff",
            password="clave",
        )
        cls.coordinador_sin_staff.groups.add(
            Group.objects.get_or_create(name="GESTION_COORDINADOR")[0]
        )

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(cls.temp_media, ignore_errors=True)

    def crear_programacion(self):
        return ProgramacionMantenimientoPreventivo.objects.create(
            cliente=self.cliente,
            sector=self.sector,
            tecnico=self.tecnico,
            fecha_programada=date.today(),
            creado_por=self.coordinador,
        )

    def preparar_preventivo(self, *, con_novedad=False):
        programacion = self.crear_programacion()
        self.client.force_login(self.usuario_tecnico)
        respuesta = self.client.get(reverse("iniciar_preventivo", args=[programacion.pk]))
        self.assertEqual(respuesta.status_code, 302)
        programacion.refresh_from_db()
        preventivo = programacion.actividad.preventivo
        preventivo.control_nivel = (
            "Se revisa el funcionamiento completo del control de nivel, "
            "sus conexiones y la respuesta durante la prueba operativa."
        )
        preventivo.tablero_electrico = (
            "Se realiza inspección visual del tablero eléctrico y prueba "
            "de operación de los elementos de mando."
        )
        preventivo.resultado_preventivo = "CON_NOVEDAD" if con_novedad else "SIN_NOVEDAD"
        preventivo.novedades = (
            "El flotador presenta desgaste y no está sellando correctamente. "
            "Se recomienda cotizar su cambio; no se reemplaza durante este preventivo."
            if con_novedad else ""
        )
        preventivo.save()
        if con_novedad:
            MedicionEquipoPreventivo.objects.create(
                preventivo=preventivo,
                nombre_equipo="Bomba No. 1",
                voltaje_medido="220 V",
                corriente_medida="8.5 A",
                estado="OPERATIVO",
                observaciones=(
                    "Equipo probado durante el mantenimiento preventivo y "
                    "en funcionamiento al finalizar la visita."
                ),
            )
        return programacion, preventivo

    def enviar_preventivo(self, programacion):
        self.client.force_login(self.usuario_tecnico)
        return self.client.post(
            reverse("formulario_preventivo", args=[programacion.pk]),
            {"accion": "finalizar"},
        )

    def test_tecnico_solo_inicia_su_programacion(self):
        programacion = self.crear_programacion()
        self.client.force_login(self.otro_usuario)
        respuesta = self.client.get(reverse("iniciar_preventivo", args=[programacion.pk]))
        self.assertEqual(respuesta.status_code, 404)
        programacion.refresh_from_db()
        self.assertEqual(programacion.estado, "PROGRAMADO")

    def test_inicio_preventivo_registra_hora_de_llegada(self):
        programacion = self.crear_programacion()
        self.client.force_login(self.usuario_tecnico)
        respuesta = self.client.get(reverse("iniciar_preventivo", args=[programacion.pk]))
        self.assertEqual(respuesta.status_code, 302)
        programacion.refresh_from_db()
        self.assertIsNotNone(programacion.actividad.hora_llegada)

    def test_preventivo_vacio_no_se_envia(self):
        programacion = self.crear_programacion()
        self.client.force_login(self.usuario_tecnico)
        self.client.get(reverse("iniciar_preventivo", args=[programacion.pk]))
        respuesta = self.client.post(
            reverse("formulario_preventivo", args=[programacion.pk]),
            {"accion": "finalizar"},
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "No se pudo enviar")
        programacion.refresh_from_db()
        self.assertEqual(programacion.estado, "EN_PROCESO")
        self.assertIsNone(programacion.actividad.numero_informe)

    def test_envio_preventivo_genera_comprobante_y_pendiente(self):
        programacion, preventivo = self.preparar_preventivo()
        respuesta = self.enviar_preventivo(programacion)
        programacion.refresh_from_db()
        preventivo.refresh_from_db()
        actividad = programacion.actividad
        actividad.refresh_from_db()
        self.assertRedirects(
            respuesta,
            reverse("comprobante_actividad", args=[actividad.pk]),
        )
        self.assertEqual(programacion.estado, "PENDIENTE_REVISION")
        self.assertEqual(preventivo.estado_revision, "PENDIENTE")
        self.assertTrue(actividad.numero_informe.startswith("PREV-"))
        self.assertIsNotNone(actividad.enviado_en)

    def test_sin_rol_no_puede_revisar(self):
        self.client.force_login(self.sin_rol)
        respuesta = self.client.get(reverse("bandeja_revision_preventivos"))
        self.assertEqual(respuesta.status_code, 403)

    def test_coordinador_no_depende_de_marca_staff_para_revisar(self):
        self.client.force_login(self.coordinador_sin_staff)
        respuesta = self.client.get(reverse("bandeja_revision_preventivos"))
        self.assertEqual(respuesta.status_code, 200)

    @override_settings(MEDIA_ROOT=tempfile.gettempdir())
    def test_coordinador_aprueba_y_publica_sin_novedad(self):
        programacion, preventivo = self.preparar_preventivo()
        self.enviar_preventivo(programacion)
        self.client.force_login(self.coordinador)
        respuesta = self.client.post(
            reverse("revisar_preventivo", args=[programacion.pk]),
            {
                "decision": "APROBAR",
                "observaciones_revision": "Informe verificado.",
                "estado_anomalia": "NO_APLICA",
            },
        )
        self.assertEqual(respuesta.status_code, 302)
        programacion.refresh_from_db()
        preventivo.refresh_from_db()
        self.assertEqual(programacion.estado, "PUBLICADO")
        self.assertEqual(preventivo.estado_revision, "PUBLICADO")
        self.assertIsNotNone(preventivo.documento_cliente_id)
        documento = DocumentoCliente.objects.get(pk=preventivo.documento_cliente_id)
        self.assertEqual(documento.estado, "PUBLICADO")
        self.assertEqual(documento.tipo, "PREVENTIVO")
        with documento.archivo.open("rb") as archivo:
            self.assertEqual(archivo.read(4), b"%PDF")

    def test_anomalia_exige_constancia_de_aviso(self):
        programacion, preventivo = self.preparar_preventivo(con_novedad=True)
        self.enviar_preventivo(programacion)
        self.client.force_login(self.supervisor)
        respuesta = self.client.post(
            reverse("revisar_preventivo", args=[programacion.pk]),
            {
                "decision": "APROBAR",
                "estado_anomalia": "PENDIENTE_RESPUESTA",
            },
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Confirme cómo se informó")
        programacion.refresh_from_db()
        self.assertEqual(programacion.estado, "PENDIENTE_REVISION")

    @override_settings(MEDIA_ROOT=tempfile.gettempdir())
    def test_anomalia_se_publica_aunque_correccion_no_este_aprobada(self):
        programacion, preventivo = self.preparar_preventivo(con_novedad=True)
        self.enviar_preventivo(programacion)
        self.client.force_login(self.supervisor)
        respuesta = self.client.post(
            reverse("revisar_preventivo", args=[programacion.pk]),
            {
                "decision": "APROBAR",
                "observaciones_revision": "Cliente pendiente de presupuesto.",
                "cliente_informado": "on",
                "medio_notificacion": "Llamada a la administración",
                "estado_anomalia": "INCLUIDO_PRESUPUESTO",
            },
        )
        self.assertEqual(respuesta.status_code, 302)
        preventivo.refresh_from_db()
        self.assertEqual(preventivo.estado_revision, "PUBLICADO")
        self.assertEqual(preventivo.estado_anomalia, "INCLUIDO_PRESUPUESTO")
        self.assertTrue(preventivo.cliente_informado)
        self.assertTrue(
            SeguimientoAnomaliaPreventivo.objects.filter(preventivo=preventivo).exists()
        )

    def test_correctivo_del_tecnico_genera_comprobante(self):
        servicio = Emergencia.objects.create(
            cliente=self.cliente,
            sector=self.sector,
            tecnico=self.tecnico,
            descripcion_falla="Bomba no arranca",
            tipo_servicio="CORRECTIVO",
        )
        self.client.force_login(self.usuario_tecnico)
        respuesta = self.client.post(
            reverse("nueva_actividad") + f"?servicio={servicio.pk}",
            {
                "servicio": str(servicio.pk),
                "tipo_actividad": "CORRECTIVO",
                "fecha": date.today().isoformat(),
                "hora_llegada": "08:00",
                "hora_salida": "09:00",
                "diagnostico": "Contactor defectuoso",
                "labor_realizada": "Se realizó ajuste y prueba",
                "resultado": "OPERATIVO",
            },
        )
        actividad = ActividadTecnico.objects.get(servicio=servicio)
        self.assertRedirects(
            respuesta,
            reverse("comprobante_actividad", args=[actividad.pk]),
        )
        self.assertTrue(actividad.numero_informe.startswith("COR-"))
        self.assertIsNotNone(actividad.enviado_en)

    def test_formulario_correctivo_no_ofrece_preventivo(self):
        servicio = Emergencia.objects.create(
            cliente=self.cliente,
            sector=self.sector,
            tecnico=self.tecnico,
            descripcion_falla="Revisión correctiva",
            tipo_servicio="CORRECTIVO",
        )
        self.client.force_login(self.usuario_tecnico)
        respuesta = self.client.get(
            reverse("nueva_actividad") + f"?servicio={servicio.pk}"
        )
        self.assertEqual(respuesta.status_code, 200)
        opciones = dict(respuesta.context["form"].fields["tipo_actividad"].choices)
        self.assertNotIn("PREVENTIVO", opciones)

    def test_correctivo_rechaza_cantidad_negativa(self):
        servicio = Emergencia.objects.create(
            cliente=self.cliente,
            sector=self.sector,
            tecnico=self.tecnico,
            descripcion_falla="Bomba no arranca",
            tipo_servicio="CORRECTIVO",
        )
        self.client.force_login(self.usuario_tecnico)
        respuesta = self.client.post(
            reverse("nueva_actividad") + f"?servicio={servicio.pk}",
            {
                "servicio": str(servicio.pk),
                "tipo_actividad": "CORRECTIVO",
                "fecha": date.today().isoformat(),
                "hora_llegada": "08:00",
                "hora_salida": "09:00",
                "labor_realizada": "Prueba",
                "resultado": "OPERATIVO",
                "es_otro[]": "1",
                "descripcion_otro[]": "Contactor",
                "cantidad[]": "-2",
            },
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "mayor que cero")
        self.assertFalse(ActividadTecnico.objects.filter(servicio=servicio).exists())

    def test_usuario_externo_no_abre_formulario_de_actividad(self):
        externo = User.objects.create_user("cliente_externo", password="clave")
        self.client.force_login(externo)
        respuesta = self.client.get(reverse("nueva_actividad"))
        self.assertEqual(respuesta.status_code, 403)
