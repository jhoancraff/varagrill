from rest_framework import serializers
from .models import VGMesa


class MesaSerializer(serializers.ModelSerializer):
    class Meta:
        model = VGMesa
        fields = ['id', 'numero', 'capacidad', 'ubicacion', 'estado']
