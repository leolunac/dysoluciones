from django.urls import path
from django.urls import path
from .views import home, dashboard, dashboard_cliente, login_view, logout_view, export_csv, export_excel, reporte_pdf
from .views import export_csv, export_excel

urlpatterns = [
    path("login/", login_view),
    path("logout/", logout_view),
    path("", home),
    path("gerencia/", dashboard),
    path("cliente/<int:cliente_id>/", dashboard_cliente),
    path("export/csv/<int:cliente_id>/", export_csv),
    path("export/excel/<int:cliente_id>/", export_excel),
    path("reporte/pdf/<int:cliente_id>/", reporte_pdf),
]