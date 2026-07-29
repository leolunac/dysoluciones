from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import DocumentoClienteForm
from .models import DocumentoCliente


@login_required
def inicio_portal(request):
    return render(request, "portal_cliente/inicio.html")


@login_required
def lista_documentos(request):
    documentos = DocumentoCliente.objects.all().order_by("-fecha_documento")

    return render(
        request,
        "portal_cliente/documentos/lista.html",
        {
            "documentos": documentos,
        },
    )


@login_required
def nuevo_documento(request):

    if request.method == "POST":
        form = DocumentoClienteForm(request.POST, request.FILES)

        if form.is_valid():
            documento = form.save()

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