from django.conf import settings
from django.core.files.storage import FileSystemStorage


class AlmacenamientoPrivado(FileSystemStorage):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("location", settings.PRIVATE_MEDIA_ROOT)
        kwargs.setdefault("base_url", None)
        super().__init__(*args, **kwargs)

    def url(self, name):
        raise ValueError("Los archivos de Gestión Humana requieren descarga autorizada.")


almacenamiento_privado = AlmacenamientoPrivado()
