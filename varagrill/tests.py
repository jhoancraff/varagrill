from django.test import TestCase

from varagrill.models import VGUsuario


class LoginViewTests(TestCase):
    def test_login_creates_session_for_valid_user(self):
        VGUsuario.objects.create_user(
            username='chef',
            password='restaurante123',
            cedula='12345678',
            email='chef@varagrill.test',
        )

        response = self.client.post('/api/auth/login/', {
            'username': 'chef',
            'password': 'restaurante123',
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['authenticated'])
        self.assertEqual(response.json()['user']['username'], 'chef')
        self.assertIn('_auth_user_id', self.client.session)
