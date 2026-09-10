import shutil
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.contrib.auth.models import Group, User
from django.test import TestCase, override_settings
from django.urls import reverse

from portal_cliente.models import DocumentoCliente

from .models import (
    Accesorio,
    AccesorioActividad,
    ActividadTecnico,
    Cliente,
    Emergencia,
    DetalleRemision,
    MantenimientoPreventivo,
    MedicionEquipoPreventivo,
    ProgramacionMantenimientoPreventivo,
    RemisionTecnico,
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

    def crear_servicio_correctivo(self):
        return Emergencia.objects.create(
            cliente=self.cliente,
            sector=self.sector,
            tecnico=self.tecnico,
            descripcion_falla="Flotador defectuoso",
            tipo_servicio="CORRECTIVO",
        )

    def crear_remision_catalogada(self, servicio, cantidad="2.00"):
        accesorio = Accesorio.objects.create(
            codigo="FLOT-PRUEBA",
            descripcion="Flotador de prueba catalogado",
        )
        remision = RemisionTecnico.objects.create(
            numero_remision=f"REM-{servicio.pk}",
            tecnico=self.tecnico,
            cliente=self.cliente,
            servicio=servicio,
            entregado_por=self.coordinador,
        )
        detalle = DetalleRemision.objects.create(
            remision=remision,
            accesorio=accesorio,
            cantidad_entregada=Decimal(cantidad),
        )
        return accesorio, remision, detalle

    def datos_nueva_remision(self, numero, servicio, accesorios):
        datos = {
            "numero_remision": numero,
            "fecha": "2026-09-10T08:00",
            "tecnico": str(self.tecnico.pk),
            "cliente": str(self.cliente.pk),
            "servicio": str(servicio.pk),
            "observaciones": "Entrega dinámica de prueba",
            "detalles-TOTAL_FORMS": str(len(accesorios)),
            "detalles-INITIAL_FORMS": "0",
            "detalles-MIN_NUM_FORMS": "1",
            "detalles-MAX_NUM_FORMS": "50",
        }
        for indice, accesorio in enumerate(accesorios):
            datos.update({
                f"detalles-{indice}-accesorio": str(accesorio.pk),
                f"detalles-{indice}-codigo_accesorio": accesorio.codigo,
                f"detalles-{indice}-descripcion_accesorio": accesorio.descripcion,
                f"detalles-{indice}-cantidad_entregada": "1",
                f"detalles-{indice}-cantidad_utilizada": "0",
                f"detalles-{indice}-cantidad_devuelta": "0",
                f"detalles-{indice}-observaciones": "",
            })
        return datos

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

    def test_remision_catalogada_alimenta_consumo_y_comprobante(self):
        servicio = self.crear_servicio_correctivo()
        accesorio, remision, detalle = self.crear_remision_catalogada(servicio)
        self.client.force_login(self.usuario_tecnico)

        respuesta = self.client.post(
            reverse("nueva_actividad") + f"?servicio={servicio.pk}",
            {
                "servicio": str(servicio.pk),
                "remision": str(remision.pk),
                "tipo_actividad": "CORRECTIVO",
                "fecha": date.today().isoformat(),
                "hora_llegada": "08:00",
                "hora_salida": "09:00",
                "diagnostico": "Flotador defectuoso",
                "labor_realizada": "Se reemplazó el flotador",
                "resultado": "OPERATIVO",
                "accesorio_id[]": str(accesorio.pk),
                "detalle_remision_id[]": str(detalle.pk),
                "cantidad[]": "1",
                "es_otro[]": "0",
                "descripcion_otro[]": "",
                "observacion[]": "Instalado en la unidad",
            },
        )

        actividad = ActividadTecnico.objects.get(servicio=servicio)
        uso = AccesorioActividad.objects.get(actividad=actividad)
        detalle.refresh_from_db()
        remision.refresh_from_db()

        self.assertRedirects(
            respuesta,
            reverse("comprobante_actividad", args=[actividad.pk]),
        )
        self.assertEqual(uso.detalle_remision_id, detalle.pk)
        self.assertEqual(detalle.cantidad_utilizada, Decimal("1.00"))
        self.assertEqual(remision.estado, "PENDIENTE")

        comprobante = self.client.get(
            reverse("comprobante_actividad", args=[actividad.pk])
        )
        self.assertContains(comprobante, remision.numero_remision)
        self.assertContains(comprobante, accesorio.descripcion)
        self.assertContains(comprobante, "Cantidad 1,00")

    def test_nueva_remision_copia_codigo_y_descripcion_del_catalogo(self):
        servicio = self.crear_servicio_correctivo()
        accesorio = Accesorio.objects.create(
            codigo="CAT-001",
            descripcion="Accesorio oficial del catálogo",
        )
        datos = {
            "numero_remision": "REM-CATALOGO-001",
            "fecha": "2026-09-09T18:00",
            "tecnico": str(self.tecnico.pk),
            "cliente": str(self.cliente.pk),
            "servicio": str(servicio.pk),
            "observaciones": "Entrega de prueba",
            "detalles-TOTAL_FORMS": "5",
            "detalles-INITIAL_FORMS": "0",
            "detalles-MIN_NUM_FORMS": "0",
            "detalles-MAX_NUM_FORMS": "1000",
            "detalles-0-accesorio": str(accesorio.pk),
            "detalles-0-codigo_accesorio": "CODIGO ALTERADO",
            "detalles-0-descripcion_accesorio": "DESCRIPCION ALTERADA",
            "detalles-0-cantidad_entregada": "2",
            "detalles-0-cantidad_utilizada": "0",
            "detalles-0-cantidad_devuelta": "0",
            "detalles-0-observaciones": "Prueba",
        }
        for indice in range(1, 5):
            datos.update({
                f"detalles-{indice}-accesorio": "",
                f"detalles-{indice}-codigo_accesorio": "",
                f"detalles-{indice}-descripcion_accesorio": "",
                f"detalles-{indice}-cantidad_entregada": "0",
                f"detalles-{indice}-cantidad_utilizada": "0",
                f"detalles-{indice}-cantidad_devuelta": "0",
                f"detalles-{indice}-observaciones": "",
            })

        self.client.force_login(self.coordinador)
        respuesta = self.client.post(reverse("nueva_remision"), datos)

        self.assertRedirects(respuesta, reverse("lista_remisiones"))
        detalle = DetalleRemision.objects.get(
            remision__numero_remision="REM-CATALOGO-001"
        )
        self.assertEqual(detalle.accesorio_id, accesorio.pk)
        self.assertEqual(detalle.codigo_accesorio, accesorio.codigo)
        self.assertEqual(detalle.descripcion_accesorio, accesorio.descripcion)

    def test_nueva_remision_inicia_con_una_fila_y_permite_agregar(self):
        self.client.force_login(self.coordinador)
        respuesta = self.client.get(reverse("nueva_remision"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "+ Agregar accesorio")
        self.assertContains(respuesta, "Quitar")
        self.assertEqual(respuesta.context["formset"].total_form_count(), 1)
        self.assertEqual(respuesta.context["formset"].max_num, 50)

    def test_nueva_remision_acepta_mas_de_cinco_accesorios(self):
        servicio = self.crear_servicio_correctivo()
        accesorios = [
            Accesorio.objects.create(
                codigo=f"DIN-{indice:03d}",
                descripcion=f"Accesorio dinámico {indice}",
            )
            for indice in range(6)
        ]
        datos = self.datos_nueva_remision(
            "REM-DINAMICA-006",
            servicio,
            accesorios,
        )

        self.client.force_login(self.coordinador)
        respuesta = self.client.post(reverse("nueva_remision"), datos)

        self.assertRedirects(respuesta, reverse("lista_remisiones"))
        remision = RemisionTecnico.objects.get(numero_remision="REM-DINAMICA-006")
        self.assertEqual(remision.detalles.count(), 6)

    def test_nueva_remision_rechaza_mas_de_cincuenta_accesorios(self):
        servicio = self.crear_servicio_correctivo()
        accesorios = [
            Accesorio.objects.create(
                codigo=f"MAX-{indice:03d}",
                descripcion=f"Accesorio máximo {indice}",
            )
            for indice in range(51)
        ]
        datos = self.datos_nueva_remision(
            "REM-DINAMICA-051",
            servicio,
            accesorios,
        )

        self.client.force_login(self.coordinador)
        respuesta = self.client.post(reverse("nueva_remision"), datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.context["formset"].non_form_errors())
        self.assertFalse(
            RemisionTecnico.objects.filter(
                numero_remision="REM-DINAMICA-051"
            ).exists()
        )

    def test_caso_completa_unidad_y_tecnico_en_remision(self):
        servicio = self.crear_servicio_correctivo()
        otra_unidad = Cliente.objects.create(
            nombre="Unidad incorrecta",
            direccion="Calle 2",
            telefono_porteria="456",
            administrador="Administración 2",
            email="otra-unidad@example.com",
            tipo_contrato="SIN_CONTRATO",
            frecuencia_lavado=6,
        )
        accesorio = Accesorio.objects.create(
            codigo="CAT-AUTO-001",
            descripcion="Accesorio para autocompletar",
        )
        datos = {
            "numero_remision": "REM-AUTO-001",
            "fecha": "2026-09-10T07:00",
            "tecnico": str(self.otro_tecnico.pk),
            "cliente": str(otra_unidad.pk),
            "servicio": str(servicio.pk),
            "observaciones": "Datos derivados del caso",
            "detalles-TOTAL_FORMS": "1",
            "detalles-INITIAL_FORMS": "0",
            "detalles-MIN_NUM_FORMS": "0",
            "detalles-MAX_NUM_FORMS": "1000",
            "detalles-0-accesorio": str(accesorio.pk),
            "detalles-0-codigo_accesorio": accesorio.codigo,
            "detalles-0-descripcion_accesorio": accesorio.descripcion,
            "detalles-0-cantidad_entregada": "1",
            "detalles-0-cantidad_utilizada": "0",
            "detalles-0-cantidad_devuelta": "0",
            "detalles-0-observaciones": "",
        }

        self.client.force_login(self.coordinador)
        respuesta = self.client.post(reverse("nueva_remision"), datos)

        self.assertRedirects(respuesta, reverse("lista_remisiones"))
        remision = RemisionTecnico.objects.get(numero_remision="REM-AUTO-001")
        self.assertEqual(remision.cliente_id, servicio.cliente_id)
        self.assertEqual(remision.tecnico_id, servicio.tecnico_id)

        datos_caso = self.client.get(
            reverse("datos_caso_remision"),
            {"servicio_id": servicio.pk},
        )
        self.assertEqual(datos_caso.status_code, 200)
        self.assertEqual(datos_caso.json()["caso"]["cliente_id"], servicio.cliente_id)
        self.assertEqual(datos_caso.json()["caso"]["tecnico_id"], servicio.tecnico_id)

    def test_correctivo_no_permite_consumir_mas_de_lo_entregado(self):
        servicio = self.crear_servicio_correctivo()
        accesorio, remision, detalle = self.crear_remision_catalogada(servicio)
        self.client.force_login(self.usuario_tecnico)

        respuesta = self.client.post(
            reverse("nueva_actividad") + f"?servicio={servicio.pk}",
            {
                "servicio": str(servicio.pk),
                "remision": str(remision.pk),
                "tipo_actividad": "CORRECTIVO",
                "fecha": date.today().isoformat(),
                "hora_llegada": "08:00",
                "hora_salida": "09:00",
                "labor_realizada": "Prueba de cantidad",
                "resultado": "OPERATIVO",
                "accesorio_id[]": str(accesorio.pk),
                "detalle_remision_id[]": str(detalle.pk),
                "cantidad[]": "3",
                "es_otro[]": "0",
                "descripcion_otro[]": "",
                "observacion[]": "",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "supera lo disponible")
        self.assertFalse(ActividadTecnico.objects.filter(servicio=servicio).exists())

    def test_conciliacion_toma_utilizado_del_informe_y_registra_devolucion(self):
        servicio = self.crear_servicio_correctivo()
        accesorio, remision, detalle = self.crear_remision_catalogada(servicio)
        actividad = ActividadTecnico.objects.create(
            tecnico=self.tecnico,
            cliente=self.cliente,
            servicio=servicio,
            remision=remision,
            tipo_actividad="CORRECTIVO",
            fecha=date.today(),
            labor_realizada="Cambio de flotador",
            registrado_por=self.usuario_tecnico,
        )
        AccesorioActividad.objects.create(
            actividad=actividad,
            accesorio=accesorio,
            detalle_remision=detalle,
            cantidad=Decimal("1.00"),
        )
        detalle.actualizar_utilizado_desde_informes()

        self.client.force_login(self.coordinador)
        formulario = self.client.get(
            reverse("conciliar_remision", args=[remision.pk])
        )
        self.assertEqual(formulario.status_code, 200)
        self.assertContains(formulario, "Del informe técnico")

        respuesta = self.client.post(
            reverse("conciliar_remision", args=[remision.pk]),
            {
                "detalles-TOTAL_FORMS": "1",
                "detalles-INITIAL_FORMS": "1",
                "detalles-MIN_NUM_FORMS": "0",
                "detalles-MAX_NUM_FORMS": "1000",
                "detalles-0-id": str(detalle.pk),
                "detalles-0-cantidad_utilizada": "2",
                "detalles-0-cantidad_devuelta": "1",
                "detalles-0-observaciones": "Accesorio devuelto al almacén",
            },
        )

        self.assertRedirects(respuesta, reverse("lista_remisiones"))
        detalle.refresh_from_db()
        remision.refresh_from_db()
        self.assertEqual(detalle.cantidad_utilizada, Decimal("1.00"))
        self.assertEqual(detalle.cantidad_devuelta, Decimal("1.00"))
        self.assertEqual(remision.estado, "CONCILIADA")

    def test_tecnico_solo_consulta_accesorios_de_su_remision(self):
        servicio = self.crear_servicio_correctivo()
        accesorio, remision, detalle = self.crear_remision_catalogada(servicio)

        self.client.force_login(self.usuario_tecnico)
        respuesta = self.client.get(
            reverse("accesorios_remision", args=[remision.pk])
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()["detalles"][0]["accesorio_id"], accesorio.pk)
        self.assertEqual(respuesta.json()["detalles"][0]["disponible"], "2.00")

        self.client.force_login(self.otro_usuario)
        respuesta = self.client.get(
            reverse("accesorios_remision", args=[remision.pk])
        )
        self.assertEqual(respuesta.status_code, 403)

    def test_coordinador_tiene_acceso_visible_y_tecnico_no_administra_remisiones(self):
        self.client.force_login(self.coordinador)
        escritorio = self.client.get(reverse("escritorio_coordinador"))
        self.assertEqual(escritorio.status_code, 200)
        self.assertContains(escritorio, reverse("lista_remisiones"))

        nueva = self.client.get(reverse("nueva_remision"))
        self.assertEqual(nueva.status_code, 200)
        self.assertContains(nueva, "Buscar en catálogo")

        self.client.force_login(self.usuario_tecnico)
        lista = self.client.get(reverse("lista_remisiones"))
        self.assertEqual(lista.status_code, 403)

    def test_menu_coordinador_sin_staff_no_muestra_mis_unidades(self):
        self.client.force_login(self.coordinador_sin_staff)
        respuesta = self.client.get(reverse("lista_remisiones"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Escritorio coordinador")
        self.assertContains(respuesta, reverse("escritorio_coordinador"))
        self.assertNotContains(respuesta, "Mis Unidades")

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

    def test_lavado_no_exige_accesorios_y_genera_comprobante_propio(self):
        servicio = Emergencia.objects.create(
            cliente=self.cliente,
            sector=self.sector,
            tecnico=self.tecnico,
            descripcion_falla="Lavado programado de tanques",
            tipo_servicio="LAVADO",
        )
        self.client.force_login(self.usuario_tecnico)

        formulario = self.client.get(
            reverse("nueva_actividad") + f"?servicio={servicio.pk}"
        )
        self.assertEqual(formulario.status_code, 200)
        self.assertEqual(
            formulario.context["form"].initial["tipo_actividad"],
            "LAVADO",
        )
        self.assertContains(formulario, "Normalmente no utiliza accesorios")

        respuesta = self.client.post(
            reverse("nueva_actividad") + f"?servicio={servicio.pk}",
            {
                "servicio": str(servicio.pk),
                "tipo_actividad": "LAVADO",
                "fecha": date.today().isoformat(),
                "hora_llegada": "08:00",
                "hora_salida": "10:00",
                "diagnostico": "Tanques programados para lavado",
                "labor_realizada": "Se realizó el lavado de los tanques.",
                "resultado": "OPERATIVO",
            },
        )

        actividad = ActividadTecnico.objects.get(servicio=servicio)
        self.assertRedirects(
            respuesta,
            reverse("comprobante_actividad", args=[actividad.pk]),
        )
        self.assertEqual(actividad.tipo_actividad, "LAVADO")
        self.assertTrue(actividad.numero_informe.startswith("LAV-"))
        self.assertEqual(actividad.accesorios_utilizados.count(), 0)

    def test_panel_tecnico_muestra_dos_accesos_principales(self):
        self.client.force_login(self.usuario_tecnico)
        respuesta = self.client.get(reverse("panel_tecnico"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Correctivos y lavados")
        self.assertContains(respuesta, "Preventivos")

    def test_usuario_externo_no_abre_formulario_de_actividad(self):
        externo = User.objects.create_user("cliente_externo", password="clave")
        self.client.force_login(externo)
        respuesta = self.client.get(reverse("nueva_actividad"))
        self.assertEqual(respuesta.status_code, 403)
