from rest_framework import serializers
from .models import VGMesa, VGProducto


class MesaSerializer(serializers.ModelSerializer):
    class Meta:
        model = VGMesa
        fields = ['id', 'numero', 'capacidad', 'ubicacion', 'estado']


class ProductoSerializer(serializers.ModelSerializer):
    categoria_nombre = serializers.CharField(source='categoria.nombre', read_only=True)

    class Meta:
        model = VGProducto
        fields = ['id', 'nombre', 'precio_venta', 'tiempo_preparacion_min', 'categoria_nombre']
