"""Pruebas de la importación local: original, fechas, acceso y repetición segura."""
import copy
import json
import tempfile
from datetime import date
from io import StringIO
from pathlib import Path
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management import call_command, CommandError
from django.db.models.deletion import ProtectedError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from .models import Cliente, SectorCliente, BitacoraOperativa, OrigenNotaKeep, Tecnico, UsuarioCliente
from .importacion_keep import leer_muestra, preparar_plan, aplicar_muestra


@override_settings(DEBUG=True)
class ImportacionKeepTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.unidad=Cliente.objects.create(nombre='Unidad Keep',tipo_contrato='SIN_CONTRATO',frecuencia_lavado=4)
        cls.sector=SectorCliente.objects.create(cliente=cls.unidad,nombre='Oficinas')
        User=get_user_model()
        cls.coord=User.objects.create_user('coord_importar')
        cls.coord.groups.add(Group.objects.get_or_create(name='GESTION_COORDINADOR')[0])
        cls.tecnico=User.objects.create_user('tecnico_importar')
        Tecnico.objects.create(user=cls.tecnico,nombre='Técnico',valor_hora_diurna=0,valor_hora_nocturna=0)
        cls.externo=User.objects.create_superuser('externo_importar',password='solo-pruebas')
        UsuarioCliente.objects.create(user=cls.externo,cliente=cls.unidad)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='sigob_keep_test_');self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'muestra.json'
        self.texto='Referencia A\nTrabajo anotado, no se infiere estado.'
        self.pendiente='Referencia B\nCliente aún por confirmar.'
        self.original={'title':'1 septiembre 2026','textContent':self.texto+'\n\n'+self.pendiente,'isTrashed':False,'textContentHtml':'<p>Original</p>','createdTimestampUsec':123456}
        self.sample={'version':1,'notes':[{'path':'Takeout/Keep/1 septiembre 2026.json','note':self.original}],
            'proposals':[{'id':1,'date':'01/09/2026','reference':'Referencia A','text':self.texto,'source':'Takeout/Keep/1 septiembre 2026.json','block_positions':[1],
                'vinculo':{'confirmado':True,'cliente_id':self.unidad.pk,'cliente_nombre':self.unidad.nombre,'sector_nombre':'Oficinas'}},
                {'id':2,'date':'01/09/2026','reference':'Referencia B','text':self.pendiente,'source':'Takeout/Keep/1 septiembre 2026.json','block_positions':[2],'vinculo':{'confirmado':False}}]}
        self.escribir()

    def escribir(self):self.path.write_text(json.dumps(self.sample,ensure_ascii=False),encoding='utf8')
    def plan(self):
        regs,lote=leer_muestra(self.path);plan,firma=preparar_plan(regs,self.coord,lote);return regs,lote,plan,firma
    def importar(self):
        regs,lote,_,firma=self.plan();return aplicar_muestra(regs,self.coord,lote,firma)

    def test_vista_previa_no_escribe(self):
        out=StringIO();call_command('importar_muestra_keep',archivo=self.path,usuario=self.coord.username,stdout=out)
        self.assertIn('NUEVA: 1',out.getvalue());self.assertIn('PENDIENTE: 1',out.getvalue())
        self.assertFalse(BitacoraOperativa.objects.exists());self.assertFalse(OrigenNotaKeep.objects.exists())

    def test_importa_solo_confirmada_con_fecha_y_texto_original(self):
        ids,_,pendientes=self.importar();self.assertEqual(pendientes,1);self.assertEqual(len(ids),1)
        b=BitacoraOperativa.objects.get();o=b.origen_keep
        self.assertEqual(b.descripcion,self.texto);self.assertEqual(o.texto_original,self.texto)
        self.assertEqual(o.nota_original,self.original);self.assertEqual(o.fecha_original,date(2026,9,1))
        self.assertEqual(b.sector,self.sector);self.assertEqual(b.cliente,self.unidad)
        self.assertEqual(b.estado,'IMPORTADO');self.assertIsNone(b.fecha_compromiso);self.assertIsNone(b.fecha_cierre)
        self.assertIsNone(b.responsable_id);self.assertIsNone(b.tecnico_id);self.assertFalse(b.visible_cliente)
        self.assertEqual(b.creado_por,self.coord);self.assertEqual(timezone.localdate(b.creado),timezone.localdate())

    def test_repeticion_no_duplica_ni_sobrescribe_edicion(self):
        regs,lote,_,firma=self.plan();aplicar_muestra(regs,self.coord,lote,firma)
        b=BitacoraOperativa.objects.get();b.estado='EN_SEGUIMIENTO';b.descripcion='Aclaración posterior';b.save()
        ids,existentes,_=aplicar_muestra(regs,self.coord,lote,firma)
        self.assertEqual(ids,[]);self.assertEqual(existentes,1)
        b.refresh_from_db();self.assertEqual(b.descripcion,'Aclaración posterior');self.assertEqual(b.estado,'EN_SEGUIMIENTO')

    def test_huella_equivocada_no_escribe(self):
        regs,lote,_,_=self.plan()
        with self.assertRaises(CommandError):aplicar_muestra(regs,self.coord,lote,'0'*64)
        self.assertFalse(BitacoraOperativa.objects.exists())

    def test_no_acepta_cambiar_texto_sin_original(self):
        self.sample['proposals'][0]['text']='Texto sustituido';self.escribir()
        with self.assertRaises(CommandError):leer_muestra(self.path)

    def test_no_acepta_fecha_distinta_del_titulo(self):
        self.sample['proposals'][0]['date']='02/09/2026';self.escribir()
        with self.assertRaises(CommandError):leer_muestra(self.path)

    def test_no_omite_bloques_originales(self):
        self.sample['proposals'].pop();self.escribir()
        with self.assertRaises(CommandError):leer_muestra(self.path)

    def test_no_importa_notas_eliminadas(self):
        self.original['isTrashed']=True;self.escribir()
        with self.assertRaises(CommandError):leer_muestra(self.path)

    def test_no_importa_bloques_duplicados(self):
        self.sample['proposals'].append(copy.deepcopy(self.sample['proposals'][0]));self.escribir()
        with self.assertRaises(CommandError):leer_muestra(self.path)

    def test_cliente_y_sector_deben_coincidir_exactamente(self):
        self.sample['proposals'][0]['vinculo']['cliente_nombre']='Nombre cambiado';self.escribir()
        with self.assertRaises(CommandError):self.plan()
        self.sample['proposals'][0]['vinculo']['cliente_nombre']=self.unidad.nombre
        self.sample['proposals'][0]['vinculo']['sector_nombre']='Viviendas';self.escribir()
        with self.assertRaises(CommandError):self.plan()

    def test_otro_texto_para_origen_importado_requiere_revision(self):
        self.importar()
        self.texto+=' Texto nuevo';self.original['textContent']=self.texto+'\n\n'+self.pendiente
        self.sample['proposals'][0]['text']=self.texto;self.escribir()
        with self.assertRaises(CommandError):self.plan()
        self.assertEqual(OrigenNotaKeep.objects.count(),1)

    def test_lote_se_revierte_completo_si_falla_la_segunda(self):
        self.sample['proposals'][1]['vinculo']=copy.deepcopy(self.sample['proposals'][0]['vinculo']);self.escribir()
        guardar=OrigenNotaKeep.save
        def fallo(obj,*a,**kw):
            if obj.referencia_original=='Referencia B':raise ValidationError('Fallo simulado')
            return guardar(obj,*a,**kw)
        with patch.object(OrigenNotaKeep,'save',fallo):
            with self.assertRaises(CommandError):self.importar()
        self.assertFalse(BitacoraOperativa.objects.exists());self.assertFalse(OrigenNotaKeep.objects.exists())

    def test_usuario_externo_o_tecnico_no_importa(self):
        regs,lote=leer_muestra(self.path)
        for user in [self.tecnico,self.externo]:
            with self.assertRaises(CommandError):preparar_plan(regs,user,lote)

    @override_settings(DEBUG=False)
    def test_comando_no_aplica_fuera_desarrollo(self):
        with self.assertRaises(CommandError):
            call_command('importar_muestra_keep',archivo=self.path,usuario=self.coord.username,aplicar=True,desarrollo=True,confirmar='0'*64,stdout=StringIO())
        self.assertFalse(BitacoraOperativa.objects.exists())

    @override_settings(DEBUG=False)
    def test_comando_produccion_requiere_doble_confirmacion(self):
        _,_,_,firma=self.plan()
        args=dict(archivo=self.path,usuario=self.coord.username,aplicar=True,produccion=True,confirmar=firma,stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command('importar_muestra_keep',**args)
        self.assertFalse(BitacoraOperativa.objects.exists())
        call_command('importar_muestra_keep',confirmar_produccion='IMPORTAR-KEEP-PRODUCCION',**args)
        self.assertEqual(BitacoraOperativa.objects.count(),1)

    def test_fecha_original_filtra_sin_cambiar_fecha_registro(self):
        self.importar();self.client.force_login(self.coord)
        BitacoraOperativa.objects.create(titulo='Actual',descripcion='Manual',creado_por=self.coord)
        r=self.client.get(reverse('lista_bitacora'),{'fecha_desde':'2026-09-01','fecha_hasta':'2026-09-01'})
        self.assertEqual(r.status_code,200)
        self.assertContains(r,'Referencia A');self.assertContains(r,'Fecha original Keep:')
        self.assertEqual(r.context['pendientes'],0)
        r=self.client.get(reverse('lista_bitacora'),{'estado':'IMPORTADO'})
        self.assertEqual(r.context['total'],1)

    def test_tecnico_no_ve_importadas_hasta_asignacion_explicita(self):
        self.importar();b=BitacoraOperativa.objects.get();self.client.force_login(self.tecnico)
        self.assertNotContains(self.client.get(reverse('lista_bitacora')),'Referencia A')
        self.assertEqual(self.client.get(reverse('historial_bitacora',args=[b.pk])).status_code,404)
        b.responsable=self.tecnico;b.save()
        r=self.client.get(reverse('historial_bitacora',args=[b.pk]))
        self.assertContains(r,'Referencia A');self.assertNotContains(r,self.pendiente)

    def test_origen_preservado_impide_borrar_novedad(self):
        self.importar()
        with self.assertRaises(ProtectedError):BitacoraOperativa.objects.get().delete()

    def test_comando_aplicacion_requiere_confirmacion(self):
        with self.assertRaises(CommandError):
            call_command('importar_muestra_keep',archivo=self.path,usuario=self.coord.username,aplicar=True,desarrollo=True,stdout=StringIO())
        _,_,_,firma=self.plan()
        out=StringIO();call_command('importar_muestra_keep',archivo=self.path,usuario=self.coord.username,aplicar=True,desarrollo=True,confirmar=firma,stdout=out)
        self.assertIn('1 nuevas',out.getvalue());self.assertEqual(BitacoraOperativa.objects.count(),1)

    def test_importado_no_es_opcion_para_notas_manuales(self):
        from .forms import BitacoraOperativaForm, SeguimientoBitacoraForm
        self.assertNotIn('IMPORTADO',dict(BitacoraOperativaForm().fields['estado'].choices))
        self.assertNotIn('IMPORTADO',dict(SeguimientoBitacoraForm().fields['estado'].choices))
        self.importar()
        self.assertIn('IMPORTADO',dict(BitacoraOperativaForm(instance=BitacoraOperativa.objects.get()).fields['estado'].choices))
