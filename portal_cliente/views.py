from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import DocumentoClienteForm
from .models import DocumentoCliente
from operacion.models import UsuarioCliente


@login_required
def inicio_portal(request):
    return render(request, "portal_cliente/inicio.html")

@login_required
def lista_documentos(request):
    documentos = (
        DocumentoCliente.objects
        .select_related("cliente")
        .all()
        .order_by("-fecha_documento", "-id")
    )

    total_documentos = documentos.count()

    total_publicados = documentos.filter(
        estado="PUBLICADO"
    ).count()

    total_borradores = documentos.filter(
        estado="BORRADOR"
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
    if request.method == "POST":
        form = DocumentoClienteForm(request.POST, request.FILES)

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
        form = DocumentoClienteForm(instance=documento)

    return render(
        request,
        "portal_cliente/documentos/editar.html",
        {
            "form": form,
            "documento": documento,
        },
    )
@login_required
def mis_documentos(request):

    usuario_cliente = get_object_or_404(
        UsuarioCliente,
        user=request.user,
    )

    documentos = (
        DocumentoCliente.objects
        .filter(
            cliente=usuario_cliente.cliente,
            estado="PUBLICADO",
        )
        .order_by("-fecha_documento", "-id")
    )

    return render(
        request,
        "portal_cliente/documentos/mis_documentos.html",
        {
            "documentos": documentos,
            "cliente": usuario_cliente.cliente,
        },
    )