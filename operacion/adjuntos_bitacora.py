"""Validación y almacenamiento privado; ninguna ruta pública de media."""
from io import BytesIO
from pathlib import Path, PurePosixPath
import hashlib
import re
import unicodedata
import warnings
from zipfile import ZipFile, BadZipFile
from xml.etree import ElementTree

from django import forms
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.files.storage import FileSystemStorage

MAX_BYTES = 10 * 1024 * 1024
TIPOS = {
    '.pdf': 'application/pdf', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
    '.png': 'image/png', '.webp': 'image/webp',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
}


def raiz_privada():
    base = Path(settings.BASE_DIR).resolve()
    configurada = getattr(settings, 'BITACORA_ADJUNTOS_ROOT', None)
    root = Path(configurada).resolve() if configurada else base.parent / (base.name + '_adjuntos_privados')
    root = root.resolve()
    publicas = [getattr(settings, 'MEDIA_ROOT', None), getattr(settings, 'STATIC_ROOT', None)]
    for entry in getattr(settings, 'STATICFILES_DIRS', []):
        publicas.append(entry[1] if isinstance(entry, (list, tuple)) else entry)
    for publica in publicas:
        if publica:
            ruta = Path(publica).resolve()
            if root.is_relative_to(ruta) or ruta.is_relative_to(root):
                raise ImproperlyConfigured('BITACORA_ADJUNTOS_ROOT debe estar separado de los directorios públicos de media y static.')
    return root


class AlmacenPrivado(FileSystemStorage):
    def url(self, name):
        raise ValueError('Los adjuntos de bitácora requieren una descarga autenticada.')


def almacenamiento_privado():
    return AlmacenPrivado(location=raiz_privada(), file_permissions_mode=0o600, directory_permissions_mode=0o700)


def ruta_para_lectura(almacen, nombre):
    if not re.fullmatch(r'[0-9a-f]{2}/[0-9a-f]{32}\.(?:pdf|jpg|jpeg|png|webp|docx|xlsx)', nombre):
        raise FileNotFoundError('Ruta de adjunto inválida')
    ruta = Path(almacen.path(nombre)).resolve()
    if not ruta.is_relative_to(raiz_privada()):
        raise FileNotFoundError('Ruta de adjunto fuera de su almacenamiento')
    return ruta


def nombre_seguro(nombre):
    nombre = unicodedata.normalize('NFC', str(nombre).replace('\\', '/').split('/')[-1])
    nombre = ''.join(c for c in nombre if not unicodedata.category(c).startswith('C'))
    nombre = nombre.strip().strip('.')
    sufijo = Path(nombre).suffix.lower()
    if sufijo not in TIPOS:
        raise ValidationError('Use PDF, JPG, PNG, WebP, DOCX o XLSX. No se admiten archivos con macros.')
    stem = nombre[:-len(sufijo)].strip()
    if not stem:
        raise ValidationError('El archivo debe tener un nombre.')
    return stem[:180] + sufijo


def validar_imagen(data, extension):
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError as exc:
        raise ImproperlyConfigured('Instale Pillow para validar imágenes de la bitácora.') from exc
    esperado = {'.jpg':'JPEG', '.jpeg':'JPEG', '.png':'PNG', '.webp':'WEBP'}[extension]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as img:
                if img.format != esperado or img.width * img.height > 40_000_000:
                    raise ValidationError('La imagen no coincide con su extensión o supera 40 megapíxeles.')
                img.verify()
            with Image.open(BytesIO(data)) as img:
                img.load()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValidationError('La imagen no es válida o está dañada.') from exc


def validar_office(data, extension):
    principal = 'word/document.xml' if extension == '.docx' else 'xl/workbook.xml'
    main_type = ('application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'
                 if extension == '.docx' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml')
    try:
        with ZipFile(BytesIO(data)) as z:
            infos = z.infolist()
            if len(infos) > 2000 or sum(i.file_size for i in infos) > 50 * 1024 * 1024:
                raise ValidationError('El documento comprimido supera los límites permitidos.')
            names = [i.filename for i in infos]
            if len(set(names)) != len(names) or '[Content_Types].xml' not in names or principal not in names:
                raise ValidationError('El documento no corresponde al formato Word o Excel indicado.')
            for item in infos:
                path = PurePosixPath(item.filename.replace('\\','/'))
                if path.is_absolute() or '..' in path.parts or ':' in item.filename or item.flag_bits & 1:
                    raise ValidationError('No se admite este contenedor de documento.')
                if 'vbaproject' in item.filename.lower():
                    raise ValidationError('No se admiten documentos con macros.')
            content_info = z.getinfo('[Content_Types].xml')
            if content_info.file_size > 256 * 1024:
                raise ValidationError('La estructura del documento es demasiado grande.')
            content = z.read(content_info)
            if b'<!DOCTYPE' in content.upper() or b'<!ENTITY' in content.upper():
                raise ValidationError('La estructura del documento no es válida.')
            doc = ElementTree.fromstring(content)
            tipos = [n.attrib.get('ContentType','').lower() for n in doc]
            if any('macroenabled' in t or 'vbaproject' in t for t in tipos):
                raise ValidationError('No se admiten documentos con macros.')
            if not any(n.attrib.get('PartName') == '/' + principal and n.attrib.get('ContentType') == main_type for n in doc):
                raise ValidationError('El tipo de documento no coincide con su extensión.')
            if z.testzip() is not None:
                raise ValidationError('El documento está dañado.')
    except (BadZipFile, KeyError, ElementTree.ParseError, RuntimeError, NotImplementedError, OSError) as exc:
        raise ValidationError('El documento Word o Excel no es válido o está dañado.') from exc


def validar_archivo(archivo):
    nombre = nombre_seguro(archivo.name)
    if archivo.size > MAX_BYTES:
        raise ValidationError('El archivo supera el máximo de 10 MB.')
    data = archivo.read(MAX_BYTES + 1)
    archivo.seek(0)
    if not data:
        raise ValidationError('El archivo está vacío.')
    if len(data) > MAX_BYTES:
        raise ValidationError('El archivo supera el máximo de 10 MB.')
    ext = Path(nombre).suffix
    if ext in {'.jpg','.jpeg','.png','.webp'}:
        validar_imagen(data, ext)
    elif ext == '.pdf':
        if not data.startswith(b'%PDF-') or b'%%EOF' not in data[-1024:]:
            raise ValidationError('El archivo no tiene una estructura PDF reconocible.')
    else:
        validar_office(data, ext)
    return {'nombre': nombre, 'extension': ext, 'data': data, 'tamano': len(data),
            'mime': TIPOS[ext], 'sha256': hashlib.sha256(data).hexdigest()}


class AdjuntoBitacoraForm(forms.Form):
    archivo = forms.FileField(label='Archivo', widget=forms.ClearableFileInput(attrs={
        'accept': ','.join(TIPOS), 'aria-describedby': 'ayuda-archivo',
    }))
    descripcion = forms.CharField(label='Descripción del soporte (opcional)', required=False, max_length=2000,
                                  widget=forms.Textarea(attrs={'rows':3}))
    confirmar = forms.BooleanField(label='He revisado el archivo seleccionado y confirmo que corresponde a esta novedad.')
    solicitud = forms.CharField(widget=forms.HiddenInput)

    def clean_archivo(self):
        return validar_archivo(self.cleaned_data['archivo'])


def guardar_archivo_privado(almacen, identificador, archivo):
    """Creación exclusiva: nunca reemplaza otro archivo y limpia escrituras fallidas."""
    import os
    nombre = f'{identificador.hex[:2]}/{identificador.hex}{archivo["extension"]}'
    root = raiz_privada()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    destino = ruta_para_lectura(almacen, nombre)
    destino.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0)
    fd = os.open(destino, flags, 0o600)
    try:
        with os.fdopen(fd, 'wb') as salida:
            salida.write(archivo['data'])
    except BaseException:
        destino.unlink(missing_ok=True)
        raise
    return nombre
