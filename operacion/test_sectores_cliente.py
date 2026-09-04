"""Sectores por cliente: aislamiento, referencias históricas y formularios reales."""
from io import StringIO
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management import call_command, CommandError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase, override_settings
from django.urls import reverse
from .models import Cliente, SectorCliente, Emergencia, BitacoraOperativa, Tecnico, SeguimientoBitacora
from .forms import NuevaLlamadaForm, GestionServicioForm, BitacoraOperativaForm


class SectoresClienteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rio=Cliente.objects.create(nombre='Torres del Río',tipo_contrato='SIN_CONTRATO',frecuencia_lavado=4)
        cls.otro=Cliente.objects.create(nombre='Otra unidad',tipo_contrato='SIN_CONTRATO',frecuencia_lavado=4)
        cls.of=SectorCliente.objects.create(cliente=cls.rio,nombre='Oficinas')
        cls.vi=SectorCliente.objects.create(cliente=cls.rio,nombre='Viviendas')
        cls.ajeno=SectorCliente.objects.create(cliente=cls.otro,nombre='Privado')
        cls.coord=get_user_model().objects.create_user('coord_sectores')
        cls.coord.groups.add(Group.objects.get_or_create(name='GESTION_COORDINADOR')[0])
        cls.user=get_user_model().objects.create_user('tecnico_sectores')
        cls.tec=Tecnico.objects.create(user=cls.user,nombre='Técnico',valor_hora_diurna=0,valor_hora_nocturna=0)
        cls.caso=Emergencia.objects.create(cliente=cls.rio,sector=cls.of,tecnico=cls.tec,descripcion_falla='Oficinas',numero_caso='SEC-1')
        Emergencia.objects.create(cliente=cls.rio,sector=cls.vi,descripcion_falla='Viviendas',numero_caso='SEC-2')
        Emergencia.objects.create(cliente=cls.rio,descripcion_falla='Anterior',numero_caso='SEC-3')
        cls.nota=BitacoraOperativa.objects.create(cliente=cls.rio,sector=cls.of,titulo='Nota oficinas',descripcion='Original',responsable=cls.user)
        BitacoraOperativa.objects.create(cliente=cls.rio,sector=cls.vi,titulo='Nota viviendas',descripcion='Original',responsable=cls.user)
        BitacoraOperativa.objects.create(cliente=cls.rio,titulo='Nota anterior',descripcion='Original',responsable=cls.user)
        BitacoraOperativa.objects.create(cliente=cls.otro,sector=cls.ajeno,titulo='Reservada',descripcion='Original',responsable=cls.coord)

    def datos_nota(self,**extra):
        return dict(titulo='Prueba',descripcion='Texto',cliente=self.rio.pk,sector=self.of.pk,tipo='NOTA_INTERNA',prioridad='MEDIA',estado='PENDIENTE',**extra)

    def test_cliente_unico_sectores_distintos(self):
        self.assertEqual(self.rio.sectores.count(),2)
        self.assertEqual(Emergencia.objects.filter(cliente=self.rio).count(),3)
        self.assertIsNone(Emergencia.objects.get(numero_caso='SEC-3').sector_id)

    def test_modelos_rechazan_sector_de_otro_cliente(self):
        for obj in [Emergencia(cliente=self.rio,sector=self.ajeno,descripcion_falla='x'),BitacoraOperativa(cliente=self.rio,sector=self.ajeno,titulo='x',descripcion='x')]:
            with self.assertRaises(ValidationError):obj.clean()

    def test_sector_requiere_cliente_en_nota(self):
        with self.assertRaises(ValidationError):
            BitacoraOperativa(sector=self.of,titulo='x',descripcion='x').clean()

    def test_formulario_llamada_guarda_sector_correcto(self):
        form=NuevaLlamadaForm(dict(cliente=self.rio.pk,sector=self.vi.pk,tipo_servicio='CORRECTIVO',prioridad='NORMAL',descripcion_falla='Nueva'))
        self.assertTrue(form.is_valid(),form.errors)
        obj=form.save();self.assertEqual(obj.sector,self.vi)

    def test_post_falsificado_y_cliente_invalido(self):
        for cliente,sector in [(self.rio.pk,self.ajeno.pk),('no-id',self.of.pk),('9'*100,self.of.pk)]:
            form=NuevaLlamadaForm(dict(cliente=cliente,sector=sector,tipo_servicio='CORRECTIVO',prioridad='NORMAL',descripcion_falla='Falsa'))
            self.assertFalse(form.is_valid());self.assertIn('sector',form.errors)

    def test_sector_vacio_permite_identificacion_posterior(self):
        datos=self.datos_nota();datos['sector']=''
        form=BitacoraOperativaForm(datos)
        self.assertTrue(form.is_valid(),form.errors)
        self.assertIsNone(form.save().sector_id)

    def test_nota_no_se_mezcla_con_otro_sector_del_caso(self):
        datos=self.datos_nota(servicio=self.caso.pk);datos['sector']=self.vi.pk
        form=BitacoraOperativaForm(datos)
        self.assertFalse(form.is_valid());self.assertIn('sector',form.errors)

    def test_servicio_no_cambia_si_hay_nota_de_sector_distinto(self):
        self.nota.servicio=self.caso;self.nota.save()
        self.caso.sector=self.vi
        with self.assertRaises(ValidationError):self.caso.clean()

    def test_tecnico_no_reclasifica_sector_por_post(self):
        form=GestionServicioForm(dict(sector=self.vi.pk,estado='EN_PROCESO'),instance=self.caso,puede_cambiar_sector=False)
        self.assertTrue(form.is_valid(),form.errors)
        self.assertEqual(form.save().sector,self.of)

    def test_filtro_bitacora_respeta_acceso_y_consolidado(self):
        self.client.force_login(self.user)
        url=reverse('lista_bitacora')
        for filtro,n in [('',3),(str(self.of.pk),1),(str(self.vi.pk),1),('sin_sector',1),(str(self.ajeno.pk),0),('x',0),('9'*100,0)]:
            r=self.client.get(url,{'sector':filtro})
            self.assertEqual(r.status_code,200)
            self.assertEqual(r.context['total'],n)
            self.assertNotContains(r,'Otra unidad')
            self.assertNotContains(r,'Reservada')

    def test_filtro_centro_servicios_y_kpis(self):
        self.client.force_login(self.coord)
        for sector,total in [('',3),(str(self.of.pk),1),('sin_sector',1),('x',0)]:
            r=self.client.get(reverse('centro_operaciones'),{'sector':sector})
            self.assertEqual(r.status_code,200)
            self.assertEqual(r.context['total'],total)
            self.assertEqual(len(r.context['ultimos_servicios']),total)

    def test_sector_en_historial_edicion_real(self):
        self.client.force_login(self.coord)
        datos=self.datos_nota();datos['sector']=self.vi.pk
        r=self.client.post(reverse('editar_bitacora',args=[self.nota.pk]),datos)
        self.assertEqual(r.status_code,302)
        entrada=SeguimientoBitacora.objects.get(bitacora=self.nota)
        cambio=next(c for c in entrada.cambios if c['campo']=='Sector')
        self.assertIn('Oficinas',cambio['anterior']);self.assertIn('Viviendas',cambio['nuevo'])
        r=self.client.get(reverse('historial_bitacora',args=[self.nota.pk]))
        self.assertContains(r,'Viviendas')

    def test_vistas_formulario_sector_y_cliente(self):
        self.client.force_login(self.coord)
        for name in ['nueva_llamada','nueva_bitacora']:
            r=self.client.get(reverse(name))
            self.assertContains(r,'id_sector');self.assertContains(r,'sectores-del-formulario')
        r=self.client.get(reverse('gestionar_servicio',args=[self.caso.pk]))
        self.assertContains(r,'Sector del servicio');self.assertContains(r,'Oficinas')

    def test_sector_nombre_duplicado_no_se_guarda(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            SectorCliente.objects.create(cliente=self.rio,nombre=' oficinas ')

    def test_referencia_sector_protegida(self):
        with self.assertRaises(ProtectedError):self.of.delete()
        self.of.cliente=self.otro
        with self.assertRaises(ValidationError):self.of.clean()

    @override_settings(DEBUG=True)
    def test_configuracion_previa_e_idempotente(self):
        cliente=Cliente.objects.create(nombre='Cliente para configurar',tipo_contrato='SIN_CONTRATO',frecuencia_lavado=4)
        anterior=Emergencia.objects.create(cliente=cliente,descripcion_falla='Anterior',numero_caso='CONFIG-1')
        args=dict(cliente=cliente.pk,nombre_exacto=cliente.nombre,stdout=StringIO())
        call_command('configurar_sectores_cliente',**args)
        self.assertEqual(cliente.sectores.count(),0)
        for _ in range(2):call_command('configurar_sectores_cliente',aplicar=True,desarrollo=True,**args)
        self.assertEqual(cliente.sectores.count(),2)
        anterior.refresh_from_db();self.assertIsNone(anterior.sector_id)
        args['nombre_exacto']='equivocado'
        with self.assertRaises(CommandError):call_command('configurar_sectores_cliente',aplicar=True,desarrollo=True,**args)

    @override_settings(DEBUG=False)
    def test_configuracion_bloqueada_fuera_desarrollo(self):
        with self.assertRaises(CommandError):
            call_command('configurar_sectores_cliente',cliente=self.rio.pk,nombre_exacto=self.rio.nombre,aplicar=True,desarrollo=True,stdout=StringIO())

    @override_settings(DEBUG=False)
    def test_configuracion_produccion_requiere_frase_exacta(self):
        cliente=Cliente.objects.create(nombre='Cliente producción',tipo_contrato='SIN_CONTRATO',frecuencia_lavado=4)
        args=dict(cliente=cliente.pk,nombre_exacto=cliente.nombre,aplicar=True,produccion=True,stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command('configurar_sectores_cliente',**args)
        self.assertEqual(cliente.sectores.count(),0)
        call_command('configurar_sectores_cliente',confirmar_produccion=f'CONFIGURAR-SECTORES-{cliente.pk}',**args)
        self.assertEqual(cliente.sectores.count(),2)
