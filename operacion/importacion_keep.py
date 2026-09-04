"""Importación explícita de la muestra revisada de Keep; sin inferencias operativas."""
import hashlib
import json
import re
import unicodedata
from datetime import date
from django.core.exceptions import ValidationError
from django.core.management.base import CommandError
from django.db import transaction, IntegrityError
from .models import BitacoraOperativa, Cliente, SectorCliente, OrigenNotaKeep
from .permisos_bitacora import puede_gestionar_bitacora


def normalizar(texto):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD', texto) if not unicodedata.combining(c)).casefold().split())


def huella(texto):
    return hashlib.sha256(texto.encode('utf-8')).hexdigest()


def fecha_titulo(titulo):
    meses = ['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre']
    coincidencia = re.fullmatch(r'(\d{1,2}) (?:de )?([a-z]+) (?:de )?(\d{4})', normalizar(titulo))
    try:
        dia, mes, anio = coincidencia.groups()
        return date(int(anio), meses.index(mes)+1, int(dia))
    except (AttributeError, ValueError):
        raise CommandError('No se puede confirmar la fecha original desde el título de Keep.')


def leer_muestra(archivo):
    if archivo.stat().st_size > 20 * 1024 * 1024:
        raise CommandError('La muestra supera 20 MB; se requiere dividirla y revisar su contenido.')
    raw = archivo.read_bytes()
    try:
        datos = json.loads(raw.decode('utf-8-sig'))
        if datos['version'] != 1 or not isinstance(datos['notes'], list) or not isinstance(datos['proposals'], list):
            raise ValueError('Formato no admitido')
        if not 0 < len(datos['proposals']) <= 5000 or not 0 < len(datos['notes']) <= 1000:
            raise ValueError('Tamaño de muestra no admitido')
        originales = {}
        for source in datos['notes']:
            path, note = source['path'], source['note']
            if not isinstance(path,str) or not path or len(path)>500 or path in originales:
                raise ValueError('Ruta original inválida o repetida')
            if not isinstance(note,dict) or not isinstance(note['title'],str) or not isinstance(note['textContent'],str) or note.get('isTrashed') or note.get('listContent'):
                raise ValueError('Se requiere nota de texto no eliminada')
            originales[path] = (note, fecha_titulo(note['title']), re.split(r'\n\s*\n', note['textContent']))
        registros = []; claves = set(); posiciones_usadas = set()
        for p in datos['proposals']:
            if not isinstance(p['reference'],str) or not 0 < len(p['reference']) <= 200:
                raise ValueError('Referencia inválida')
            if not isinstance(p['text'],str) or not p['text'].strip():
                raise ValueError('Texto vacío')
            nota, fecha, bloques = originales[p['source']]
            if fecha.strftime('%d/%m/%Y') != p['date']:
                raise ValueError('Fecha distinta a la del título original')
            positions = p['block_positions']
            if not isinstance(positions,list) or not positions or any(type(n) is not int for n in positions) or positions != sorted(set(positions)):
                raise ValueError('Posiciones de bloques inválidas')
            textos=[]
            for n in positions:
                if n<1 or n>len(bloques) or (p['source'],n) in posiciones_usadas:
                    raise ValueError('Bloque repetido o fuera de la nota original')
                posiciones_usadas.add((p['source'],n))
                texto=bloques[n-1].strip()
                if not texto or normalizar(texto.splitlines()[0]) != normalizar(p['reference']):
                    raise ValueError('El bloque no corresponde a la referencia')
                textos.append(texto)
            if '\n\n'.join(textos) != p['text']:
                raise ValueError('El texto propuesto no coincide con los bloques originales')
            vinculo=p['vinculo']
            if not isinstance(vinculo,dict) or type(vinculo['confirmado']) is not bool:
                raise ValueError('Confirmación de cliente inválida')
            if vinculo['confirmado']:
                if type(vinculo['cliente_id']) is not int or vinculo['cliente_id'] <= 0 or not isinstance(vinculo['cliente_nombre'],str) or not isinstance(vinculo['sector_nombre'],str):
                    raise ValueError('Vínculo confirmado incompleto')
            clave=huella(json.dumps([fecha.isoformat(),normalizar(p['reference'])],ensure_ascii=False))
            if clave in claves:
                raise ValueError('Más de una propuesta para el mismo día y referencia; requiere revisión')
            claves.add(clave)
            registros.append(dict(propuesta=p,fecha=fecha,nota=nota,clave=clave,huella_texto=huella(p['text'])))
        esperadas={(path,n) for path,(_,_,bloques) in originales.items() for n,b in enumerate(bloques,1) if b.strip()}
        if posiciones_usadas != esperadas:
            raise ValueError('La muestra omite bloques de las notas originales')
        return registros, hashlib.sha256(raw).hexdigest()
    except (KeyError, TypeError, ValueError, IndexError, UnicodeError) as exc:
        raise CommandError(f'Muestra inválida: {exc}') from exc


def preparar_plan(registros, usuario, lote):
    if not usuario.is_active or not puede_gestionar_bitacora(usuario):
        raise CommandError('El usuario indicado debe ser un gestor activo de la bitácora, sin perfil externo.')
    plan=[]
    for r in registros:
        p=r['propuesta'];v=p['vinculo'];item=dict(r)
        if not v['confirmado']:
            item['accion']='PENDIENTE';plan.append(item);continue
        try:
            cliente=Cliente.objects.get(pk=v['cliente_id'],nombre=v['cliente_nombre'])
        except Cliente.DoesNotExist:
            raise CommandError(f"No coincide el cliente confirmado para {p['reference']}. No se importó ninguna nota.")
        sector=None
        if v['sector_nombre']:
            try:
                sector=SectorCliente.objects.get(cliente=cliente,nombre=v['sector_nombre'])
            except SectorCliente.DoesNotExist:
                raise CommandError(f"Falta el sector confirmado {v['sector_nombre']} de {cliente.nombre}.")
        item.update(cliente=cliente,sector=sector)
        anterior=OrigenNotaKeep.objects.filter(clave=r['clave']).first()
        if anterior:
            if anterior.huella_texto != r['huella_texto'] or anterior.vinculo_importado != v:
                raise CommandError(f"La nota {p['date']} — {p['reference']} ya tiene otra versión o vínculo importado. Revise su historial; no se sobrescribió.")
            item['accion']='YA IMPORTADA'
        else:
            item['accion']='NUEVA'
        plan.append(item)
    firma=huella(json.dumps(dict(lote=lote,usuario=usuario.pk,nombre_usuario=usuario.get_username(),
        vinculos=[dict(clave=i['clave'],cliente=i['cliente'].pk,sector=i['sector'].pk if i['sector'] else None) for i in plan if i['accion']!='PENDIENTE']),sort_keys=True))
    return plan,firma


def aplicar_muestra(registros, usuario, lote, confirmar):
    try:
        with transaction.atomic():
            # Orden estable; dos ejecuciones sobre los mismos clientes se serializan.
            ids=sorted({r['propuesta']['vinculo']['cliente_id'] for r in registros if r['propuesta']['vinculo']['confirmado']})
            list(Cliente.objects.select_for_update().filter(pk__in=ids).order_by('pk'))
            usuario=type(usuario).objects.get(pk=usuario.pk)
            plan,firma=preparar_plan(registros,usuario,lote)
            if firma != confirmar:
                raise CommandError('La revisión no coincide con la muestra, usuario o vínculos actuales. Ejecute primero la vista previa.')
            nuevas=[];existentes=0;pendientes=0
            for item in plan:
                if item['accion']=='PENDIENTE':pendientes+=1;continue
                if item['accion']=='YA IMPORTADA':existentes+=1;continue
                p=item['propuesta']
                b=BitacoraOperativa(titulo=('Keep · '+p['reference'])[:180],descripcion=p['text'],
                    cliente=item['cliente'],sector=item['sector'],estado='IMPORTADO',tipo='NOTA_INTERNA',
                    prioridad='MEDIA',creado_por=usuario,responsable=None,tecnico=None,visible_cliente=False)
                b.full_clean();b.save()
                origen=OrigenNotaKeep(bitacora=b,clave=item['clave'],huella_texto=item['huella_texto'],
                    fecha_original=item['fecha'],referencia_original=p['reference'],archivo_original=p['source'],
                    texto_original=p['text'],nota_original=item['nota'],posiciones=p['block_positions'],
                    vinculo_importado=p['vinculo'],lote_sha256=lote)
                origen.full_clean();origen.save();nuevas.append(b.pk)
            return nuevas,existentes,pendientes
    except IntegrityError as exc:
        raise CommandError('Conflicto de datos durante la importación. Se canceló el lote completo; ejecute de nuevo la vista previa.') from exc
    except ValidationError as exc:
        raise CommandError(f'No se pudo validar una nota; se canceló todo el lote: {exc}') from exc
