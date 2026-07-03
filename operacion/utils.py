from .models import EventoServicio


def registrar_evento(servicio, titulo, descripcion="", usuario="", icono="📌"):
    """
    Registra un evento en la línea de tiempo de un servicio.
    """

    EventoServicio.objects.create(
        servicio=servicio,
        titulo=titulo,
        descripcion=descripcion,
        usuario=usuario,
        icono=icono,
    )