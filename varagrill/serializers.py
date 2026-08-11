from rest_framework import serializers
from .models import VGMesa, VGProducto


class MesaSerializer(serializers.ModelSerializer):
    class Meta:
        model = VGMesa
        fields = ['id', 'numero', 'capacidad', 'ubicacion', 'estado']


class ProductoSerializer(serializers.ModelSerializer):
    categoria_nombre = serializers.CharField(source='categoria.nombre', read_only=True)
    imagen_url = serializers.SerializerMethodField()
    composicion = serializers.SerializerMethodField()

    def get_imagen_url(self, obj):
        if not obj.imagen_url:
            return ''
        return f'/api/productos/{obj.id}/imagen/'

    def get_composicion(self, obj):
        return obj.nombres_composicion()

    class Meta:
        model = VGProducto
        fields = ['id', 'nombre', 'descripcion', 'precio_venta', 'venta_por_peso', 'tiempo_preparacion_min', 'categoria_nombre', 'imagen_url', 'composicion']