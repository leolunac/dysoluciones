from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/",include("django.contrib.auth.urls"),
),
    path("portal/", include("portal_cliente.urls")),
    path("", include("operacion.urls")),
    path(
        "gestion-comercial/",
        include("gestion_comercial.urls"),
    ),
    ]
if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )