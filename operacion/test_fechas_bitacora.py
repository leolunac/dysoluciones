"""Fechas de registro en la zona horaria local y alcance de autorización."""
from datetime import date, datetime, timezone as dt_timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import BitacoraOperativa, Cliente, Tecnico, UsuarioCliente


@override_settings(TIME_ZONE='America/Bogota', USE_TZ=True)
class FechasBitacoraTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.coord = User.objects.create_user(username='coord_fechas')
        cls.coord.groups.add(Group.objects.get_or_create(name='GESTION_COORDINADOR')[0])
        cls.andy = User.objects.create_user(username='andy_fechas')
        Tecnico.objects.create(user=cls.andy, nombre='Andy prueba', valor_hora_diurna=0, valor_hora_nocturna=0)
        cls.cliente_user = User.objects.create_user(username='cliente_fechas')
        unidad = Cliente.objects.create(nombre='Unidad de prueba',tipo_contrato='SIN_CONTRATO',frecuencia_lavado=4)
        UsuarioCliente.objects.create(user=cls.cliente_user,cliente=unidad)
        cls.ids=[]
        for i, (timestamp, user, state) in enumerate([
            ('2026-09-04T04:59:00',cls.coord,'PENDIENTE'),
            ('2026-09-04T05:00:00',cls.andy,'PENDIENTE'),
            ('2026-09-05T04:59:00',cls.coord,'CERRADO'),
            ('2026-09-05T05:00:00',cls.coord,'PENDIENTE'),
        ]):
            registro = BitacoraOperativa.objects.create(titulo=f'Fecha {i}',descripcion='Prueba sello',responsable=user,estado=state)
            BitacoraOperativa.objects.filter(pk=registro.pk).update(creado=datetime.fromisoformat(timestamp).replace(tzinfo=dt_timezone.utc))
            cls.ids.append(registro.pk)

    def setUp(self):
        self.enterContext(timezone.override('America/Bogota'))
        self.client.force_login(self.coord)

    def get(self, **params):
        return self.client.get(reverse('lista_bitacora'), params)

    def ids_response(self, response):
        return list(response.context['registros'].values_list('pk',flat=True))

    def test_sin_fechas_conserva_todos_los_registros_visibles(self):
        r=self.get()
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.context['total'],4)
        self.assertCountEqual(self.ids_response(r),self.ids)
        self.assertContains(r,'Novedades de todas las fechas')

    def test_dia_inclusivo_respeta_medianoche_de_colombia(self):
        r=self.get(fecha_desde='2026-09-04',fecha_hasta='2026-09-04')
        self.assertEqual(r.status_code,200)
        self.assertEqual(self.ids_response(r),[self.ids[2],self.ids[1]])
        self.assertEqual(r.context['total'],2)
        self.assertEqual(r.context['pendientes'],1)
        self.assertContains(r,'Novedades del 04/09/2026')
        self.assertContains(r,'04/09/2026 00:00')
        self.assertContains(r,'04/09/2026 23:59')

    def test_intervalos_abiertos_y_rango_completo(self):
        self.assertCountEqual(self.ids_response(self.get(fecha_desde='2026-09-04')),self.ids[1:])
        self.assertCountEqual(self.ids_response(self.get(fecha_hasta='2026-09-04')),self.ids[:3])
        self.assertCountEqual(self.ids_response(self.get(fecha_desde='2026-09-03',fecha_hasta='2026-09-05')),self.ids)

    def test_fechas_combinadas_con_busqueda_y_estado(self):
        r=self.get(fecha_desde='2026-09-04',fecha_hasta='2026-09-04',buscar='sello',estado='CERRADO')
        self.assertEqual(self.ids_response(r),[self.ids[2]])
        self.assertEqual(r.context['total'],1)
        self.assertEqual(r.context['pendientes'],0)
        self.assertEqual(self.get(fecha_desde='2026-09-04',buscar='no existe').context['total'],0)

    @patch('operacion.views.timezone.localdate',return_value=date(2026,9,4))
    def test_hoy_y_ayer_reemplazan_fechas_y_conservan_otros_filtros(self, _):
        r=self.get(periodo='hoy',fecha_desde='incorrecta',fecha_hasta='2000-01-01',estado='PENDIENTE')
        self.assertEqual(r.status_code,200)
        self.assertEqual(self.ids_response(r),[self.ids[1]])
        self.assertEqual(r.context['filtro_fecha_desde'],'2026-09-04')
        self.assertEqual(r.context['filtro_fecha_hasta'],'2026-09-04')
        self.assertEqual(self.ids_response(self.get(periodo='ayer')),[self.ids[0]])

    def test_fechas_invalidas_no_devuelven_toda_la_bitacora(self):
        cases=[{'fecha_desde':'abc'},{'fecha_hasta':'2026-02-29'},{'fecha_desde':'20260904'}, {'fecha_desde':'2026-09-05','fecha_hasta':'2026-09-04'}]
        for params in cases:
            with self.subTest(params=params):
                r=self.get(**params)
                self.assertEqual(r.status_code,400)
                self.assertEqual(r.context['total'],0)
                self.assertTrue(r.context['errores_fechas'])
                self.assertContains(r,'Revise las fechas del filtro',status_code=400)

    def test_tecnico_solo_ve_sus_asignaciones_dentro_del_periodo(self):
        self.client.force_login(self.andy)
        r=self.get(fecha_desde='2026-09-04',fecha_hasta='2026-09-04')
        self.assertEqual(self.ids_response(r),[self.ids[1]])
        self.assertEqual(r.context['total'],1)
        self.assertNotContains(r,reverse('nueva_bitacora'))
        self.assertNotContains(r,reverse('editar_bitacora',args=[self.ids[1]]))
        self.assertEqual(self.get(fecha_desde='2026-09-05').context['total'],0)

    def test_cliente_no_accede_con_parametros_de_fecha(self):
        self.client.force_login(self.cliente_user)
        self.assertEqual(self.get(periodo='hoy').status_code,403)
        self.assertEqual(self.get(fecha_desde='2026-01-01').status_code,403)
