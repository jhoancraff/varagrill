from rest_framework import serializers
from .models import VGMesa, VGProducto


class MesaSerializer(serializers.ModelSerializer):
    class Meta:
        model = VGMesa
        fields = ['id', 'numero', 'capacidad', 'ubicacion', 'estado']


class ProductoSerializer(serializers.ModelSerializer):
    categoria_nombre = serializers.CharField(source='categoria.nombre', read_only=True)
    categoria_arma_plato_automatico = serializers.BooleanField(source='categoria.arma_plato_automatico', read_only=True)
    imagen_url = serializers.SerializerMethodField()
    composicion = serializers.SerializerMethodField()
    grupos_opciones = serializers.SerializerMethodField()

    def get_imagen_url(self, obj):
        if not obj.imagen_url:
            return ''
        # El endpoint es siempre /api/productos/<id>/imagen/ sin importar el archivo
        # real: sin este "cache-bust" por fecha_actualizacion, el navegador sigue
        # sirviendo la imagen vieja despues de reemplazarla (mismo criterio que
        # _product_image_url en api_views.py).
        version = int(obj.fecha_actualizacion.timestamp()) if obj.fecha_actualizacion else 0
        return f'/api/productos/{obj.id}/imagen/?v={version}'

    def get_composicion(self, obj):
        return obj.nombres_composicion()

    def get_grupos_opciones(self, obj):
        return [
            {
                'id': grupo.id,
                'nombre': grupo.nombre,
                'obligatorio': grupo.obligatorio,
                'seleccion_multiple': grupo.seleccion_multiple,
                'categoria_opciones_id': grupo.categoria_opciones_id,
                'maximo_selecciones': grupo.maximo_selecciones,
                'opciones': [
                    {
                        'id': opcion.id,
                        'preparacion_id': opcion.preparacion_id,
                        'nombre': opcion.preparacion.nombre,
                        'precio_adicional': str(opcion.precio_adicional),
                    }
                    for opcion in grupo.opciones.all()
                ],
            }
            for grupo in obj.grupos_opciones.all()
        ]

    class Meta:
        model = VGProducto
        fields = [
            'id', 'nombre', 'descripcion', 'precio_venta', 'venta_por_peso', 'tiempo_preparacion_min',
            'categoria_id', 'categoria_nombre', 'categoria_arma_plato_automatico', 'imagen_url',
            'composicion', 'grupos_opciones',
        ]
