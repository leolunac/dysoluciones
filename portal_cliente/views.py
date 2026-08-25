from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from operacion.models import UsuarioCliente, Cliente
from operacion.views import usuario_puede_ver_cliente
from .forms import DocumentoClienteForm
from .models import DocumentoCliente


def validar_usuario_interno(request):
    """
    Permite administrar documentos únicamente a usuarios internos.
    """
    if not request.user.is_staff:
        raise PermissionDenied(
            "No tiene permisos para administrar documentos."
        )


@login_required
def inicio_portal(request):
    validar_usuario_interno(request)

    return render(
        request,
        "portal_cliente/inicio.html",
    )


@login_required
def lista_documentos(request):
    validar_usuario_interno(request)

    documentos = (
        DocumentoCliente.objects
        .select_related("cliente")
        .all()
        .order_by("-fecha_documento", "-id")
    )

    total_documentos = documentos.count()

    total_publicados = documentos.filter(
        estado="PUBLICADO",
    ).count()

    total_borradores = documentos.filter(
        estado="BORRADOR",
    ).count()

    total_clientes = (
        documentos
        .values("cliente_id")
        .distinct()
        .count()
    )

    contexto = {
        "documentos": documentos,
        "total_documentos": total_documentos,
        "total_publicados": total_publicados,
        "total_borradores": total_borradores,
        "total_clientes": total_clientes,
    }

    return render(
        request,
        "portal_cliente/documentos/lista.html",
        contexto,
    )


@login_required
def nuevo_documento(request):
    validar_usuario_interno(request)

    if request.method == "POST":
        form = DocumentoClienteForm(
            request.POST,
            request.FILES,
        )

        if form.is_valid():
            form.save()
            return redirect("lista_documentos")
    else:
        form = DocumentoClienteForm()

    return render(
        request,
        "portal_cliente/documentos/nuevo.html",
        {
            "form": form,
        },
    )


@login_required
def editar_documento(request, documento_id):
    validar_usuario_interno(request)

    documento = get_object_or_404(
        DocumentoCliente,
        id=documento_id,
    )

    if request.method == "POST":
        form = DocumentoClienteForm(
            request.POST,
            request.FILES,
            instance=documento,
        )

        if form.is_valid():
            form.save()
            return redirect("lista_documentos")
    else:
        form = DocumentoClienteForm(
            instance=documento,
        )

    return render(
        request,
        "portal_cliente/documentos/editar.html",
        {
            "form": form,
            "documento": documento,
        },
    )

@login_required
def mis_documentos(request, cliente_id=None):

    # =========================================
    # USUARIO DE ADMINISTRACION / MULTIUNIDAD
    # =========================================
    if cliente_id is not None:

        if not usuario_puede_ver_cliente(
            request.user,
            cliente_id,
        ):
            raise PermissionDenied(
                "No está autorizado para consultar los documentos de esta unidad."
            )

        cliente = get_object_or_404(
            Cliente,
            id=cliente_id,
            activo=True,
        )

    else:

        # =========================================
        # CLIENTE TRADICIONAL
        # =========================================
        usuario_cliente = get_object_or_404(
            UsuarioCliente,
            user=request.user,
        )

        cliente = usuario_cliente.cliente

    documentos = (
        DocumentoCliente.objects
        .filter(
            cliente=cliente,
            estado="PUBLICADO",
        )
        .order_by("-fecha_documento", "-id")
    )

    return render(
        request,
        "portal_cliente/documentos/mis_documentos.html",
        {
            "documentos": documentos,
            "cliente": cliente,
        },
    )
