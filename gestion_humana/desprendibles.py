from django import forms
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from django.utils import timezone

from .models import DesprendiblePago, Empleado


def es_gestion_humana(user):
    return user.is_authenticated and user.is_active and user.groups.filter(name='GESTION_HUMANA').exists()


class DesprendibleForm(forms.ModelForm):
    class Meta:
        model = DesprendiblePago
        fields = ('empleado', 'periodo_inicio', 'periodo_fin', 'archivo')
        widgets = {'periodo_inicio': forms.DateInput(attrs={'type': 'date'}), 'periodo_fin': forms.DateInput(attrs={'type': 'date'})}
        labels = {'periodo_inicio': 'Inicio de la quincena', 'periodo_fin': 'Fin de la quincena', 'archivo': 'Archivo PDF'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['empleado'].queryset = Empleado.objects.filter(tipo_empleado='TECNICO', tecnico__isnull=False, estado='ACTIVO').order_by('apellidos', 'nombres')

    def clean(self):
        datos = super().clean()
        empleado = datos.get('empleado')
        inicio = datos.get('periodo_inicio')
        fin = datos.get('periodo_fin')
        if empleado and inicio and fin and DesprendiblePago.objects.filter(
            empleado=empleado,
            periodo_inicio=inicio,
            periodo_fin=fin,
            activo=True,
        ).exists():
            raise ValidationError(
                'Ya existe un desprendible activo para este técnico y período.'
            )
        return datos

    def clean_archivo(self):
        archivo = self.cleaned_data['archivo']
        if archivo.read(5) != b'%PDF-':
            raise ValidationError('Seleccione un archivo PDF válido.')
        archivo.seek(0)
        return archivo


@login_required
@never_cache
@require_http_methods(['GET', 'POST'])
def administrar(request):
    if not es_gestion_humana(request.user):
        raise PermissionDenied
    form = DesprendibleForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        registro = form.save(commit=False)
        registro.creado_por = request.user
        registro.save()
        return redirect('gestion_humana:desprendibles_administrar')
    registros = DesprendiblePago.objects.filter(activo=True).select_related('empleado')
    return render(request, 'gestion_humana/desprendibles_admin.html', {'form': form, 'registros': registros})


@login_required
@never_cache
@require_GET
def mis_desprendibles(request):
    if not request.user.is_active:
        raise PermissionDenied
    registros = DesprendiblePago.objects.filter(activo=True, empleado__tecnico__user=request.user, empleado__tecnico__activo=True).order_by('-periodo_fin', '-pk')
    return render(request, 'gestion_humana/mis_desprendibles.html', {'registros': registros})


@login_required
@never_cache
@require_GET
def descargar(request, pk):
    registro = get_object_or_404(DesprendiblePago.objects.filter(activo=True).select_related('empleado__tecnico'), pk=pk)
    tecnico = registro.empleado.tecnico
    if not (es_gestion_humana(request.user) or (request.user.is_active and tecnico and tecnico.activo and tecnico.user_id == request.user.pk)):
        raise Http404
    try:
        archivo = registro.archivo.open('rb')
    except (FileNotFoundError, OSError):
        raise Http404
    respuesta = FileResponse(archivo, as_attachment=request.GET.get('ver') != '1', filename='desprendible.pdf', content_type='application/pdf')
    respuesta['X-Content-Type-Options'] = 'nosniff'
    return respuesta


@login_required
@never_cache
@require_POST
def retirar_desprendible(request, pk):
    if not es_gestion_humana(request.user):
        raise PermissionDenied
    DesprendiblePago.objects.filter(pk=pk, activo=True).update(
        activo=False, retirado_por=request.user, retirado=timezone.now()
    )
    return redirect('gestion_humana:desprendibles_administrar')
