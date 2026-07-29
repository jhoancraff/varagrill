import json

from django.contrib.auth import authenticate, login
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework import generics

from .models import VGMesa
from .serializers import MesaSerializer


class MesaListView(generics.ListAPIView):
    queryset = VGMesa.objects.all().order_by('numero')
    serializer_class = MesaSerializer


@method_decorator(csrf_exempt, name='dispatch')
class LoginView(generics.GenericAPIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request, *args, **kwargs):
        if request.content_type and 'application/json' in request.content_type:
            data = json.loads(request.body.decode('utf-8')) if request.body else {}
        else:
            data = request.POST.dict()

        username = str(data.get('username', '')).strip()
        password = str(data.get('password', ''))

        user = authenticate(request, username=username, password=password)
        if user is None:
            return JsonResponse({'authenticated': False, 'message': 'Credenciales inválidas'}, status=401)

        login(request, user)
        return JsonResponse({
            'authenticated': True,
            'message': 'Bienvenido al sistema',
            'user': {
                'username': user.username,
                'email': user.email,
            },
        })
