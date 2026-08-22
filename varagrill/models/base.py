from django.conf import settings
from django.db import models


# ---------------------------------------------------------------------------
# Auditoría reutilizable (creado_por / fecha_creacion / actualizado_por / fecha_actualizacion)
# ---------------------------------------------------------------------------
class VGAuditoria(models.Model):
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="%(class)s_creados",
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="%(class)s_actualizados",
    )
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
