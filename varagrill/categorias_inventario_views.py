"""
Categorias del inventario (Condimentos, Carnes, Granos, Bolsas, Cajas...): crear y renombrar
o desactivar. Clasifican a los ingredientes (VGIngrediente.categoria) para filtrar el
inventario y para imprimirlo por categoria (ver reportes_pdf_views.reporte_inventario_pdf_view).

No se borran: desactivar una categoria la quita de los selectores sin perder la clasificacion
de los ingredientes que ya la tienen. Asignar ingredientes (uno o en lote) vive en
api_views.admin_catalog_view (tipo 'asignar_categoria' y 'actualizar_ingrediente').
"""
import json

from django.db.models import Count
from django.views.decorators.csrf import csrf_exempt

from .auth_helpers import _auth_response, _is_admin_user
from .models import VGCategoriaIngrediente

LARGO_MAXIMO_NOMBRE = 80


def _serialize_categoria(categoria, cantidad):
    return {
        'id': categoria.id,
        'nombre': categoria.nombre,
        'activo': categoria.activo,
        'ingredientes': cantidad,
    }


def _nombre_valido(data, excluir_id=None):
    """Devuelve (nombre, mensaje_de_error)."""
    nombre = ' '.join(str(data.get('nombre', '') or '').split())
    if not nombre:
        return None, 'El nombre de la categoría es obligatorio.'
    if len(nombre) > LARGO_MAXIMO_NOMBRE:
        return None, f'El nombre no puede pasar de {LARGO_MAXIMO_NOMBRE} caracteres.'
    repetida = VGCategoriaIngrediente.objects.filter(nombre__iexact=nombre)
    if excluir_id is not None:
        repetida = repetida.exclude(pk=excluir_id)
    if repetida.exists():
        return None, 'Ya existe una categoría con ese nombre.'
    return nombre, None


@csrf_exempt
def admin_categorias_inventario_view(request):
    if request.method not in ('GET', 'POST'):
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)
    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    def listado():
        categorias = VGCategoriaIngrediente.objects.annotate(cantidad=Count('ingredientes')).order_by('nombre')
        return [_serialize_categoria(categoria, categoria.cantidad) for categoria in categorias]

    if request.method == 'GET':
        from .models import VGIngrediente
        return _auth_response({
            'ok': True,
            'categorias': listado(),
            'sin_categoria': VGIngrediente.objects.filter(categoria__isnull=True).count(),
        })

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    action = str(data.get('action', '')).strip().lower()

    if action == 'create':
        nombre, error = _nombre_valido(data)
        if error:
            return _auth_response({'ok': False, 'message': error}, status=400)
        categoria = VGCategoriaIngrediente.objects.create(
            nombre=nombre, creado_por=request.user, actualizado_por=request.user,
        )
        return _auth_response({
            'ok': True,
            'message': f'Categoría «{categoria.nombre}» creada.',
            'categoria': _serialize_categoria(categoria, 0),
            'categorias': listado(),
        }, status=201)

    if action == 'update':
        try:
            categoria = VGCategoriaIngrediente.objects.get(pk=int(data.get('id')))
        except (TypeError, ValueError, VGCategoriaIngrediente.DoesNotExist):
            return _auth_response({'ok': False, 'message': 'La categoría no existe.'}, status=400)

        campos = ['actualizado_por', 'fecha_actualizacion']
        if 'nombre' in data:
            nombre, error = _nombre_valido(data, excluir_id=categoria.pk)
            if error:
                return _auth_response({'ok': False, 'message': error}, status=400)
            categoria.nombre = nombre
            campos.append('nombre')
        if 'activo' in data:
            categoria.activo = bool(data.get('activo'))
            campos.append('activo')
        categoria.actualizado_por = request.user
        categoria.save(update_fields=campos)
        return _auth_response({
            'ok': True,
            'message': f'Categoría «{categoria.nombre}» actualizada.',
            'categorias': listado(),
        })

    return _auth_response({'ok': False, 'message': 'Accion invalida.'}, status=400)
