from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from apps.customers.models import CustomerProfile

User = get_user_model()


class AuthTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.register_url = '/api/auth/register/'
        self.login_url = '/api/auth/login/'
        self.logout_url = '/api/auth/logout/'
        self.refresh_url = '/api/auth/token/refresh/'
        self.me_url = '/api/auth/me/'

        self.valid_payload = {
            'full_name': 'Kavitha Nair',
            'email': 'kavitha@nairbakery.in',
            'mobile_number': '9847123456',
            'password': 'StrongPassword123!',
            'password_confirmation': 'StrongPassword123!',
            'business_name': 'Nair Traditional Bakery',
            'business_type': 'bakery',
            'gstin': '32AAAAA0000A1Z5',
        }

    def test_customer_registration_success(self):
        res = self.client.post(self.register_url, self.valid_payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['status'], 'success')
        self.assertEqual(res.data['user']['email'], 'kavitha@nairbakery.in')
        self.assertEqual(res.data['user']['role'], 'customer')

        # Verify in DB
        user = User.objects.get(email='kavitha@nairbakery.in')
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.is_active)
        self.assertTrue(hasattr(user, 'customer_profile'))
        self.assertEqual(user.customer_profile.business_name, 'Nair Traditional Bakery')
        self.assertEqual(user.customer_profile.gstin, '32AAAAA0000A1Z5')

        # Verify HttpOnly cookie set
        self.assertIn('onfresh_access_token', res.cookies)
        self.assertIn('onfresh_refresh_token', res.cookies)
        self.assertTrue(res.cookies['onfresh_access_token']['httponly'])

    def test_duplicate_email_rejection(self):
        self.client.post(self.register_url, self.valid_payload, format='json')
        # Try registering with same email (different case)
        duplicate_payload = self.valid_payload.copy()
        duplicate_payload['email'] = 'KAVITHA@nairbakery.in'
        res = self.client.post(self.register_url, duplicate_payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', res.data['errors'])

    def test_password_mismatch_rejection(self):
        payload = self.valid_payload.copy()
        payload['email'] = 'mismatch@example.com'
        payload['password_confirmation'] = 'DifferentPassword123!'
        res = self.client.post(self.register_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password_confirmation', res.data['errors'])

    def test_invalid_short_password_rejection(self):
        payload = self.valid_payload.copy()
        payload['email'] = 'short@example.com'
        payload['password'] = 'short'
        payload['password_confirmation'] = 'short'
        res = self.client.post(self.register_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_role_escalation_prevention_on_registration(self):
        # Malicious payload trying to register as admin / staff
        payload = self.valid_payload.copy()
        payload['email'] = 'hacker@example.com'
        payload['is_staff'] = True
        payload['is_superuser'] = True
        payload['role'] = 'admin'
        res = self.client.post(self.register_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        user = User.objects.get(email='hacker@example.com')
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(res.data['user']['role'], 'customer')

    def test_login_success(self):
        self.client.post(self.register_url, self.valid_payload, format='json')
        res = self.client.post(self.login_url, {
            'email': 'kavitha@nairbakery.in',
            'password': 'StrongPassword123!'
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['status'], 'success')
        self.assertIn('onfresh_access_token', res.cookies)

    def test_login_failure_invalid_credentials(self):
        self.client.post(self.register_url, self.valid_payload, format='json')
        res = self.client.post(self.login_url, {
            'email': 'kavitha@nairbakery.in',
            'password': 'WrongPassword123!'
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('detail', res.data)

    def test_me_authenticated_via_cookie(self):
        login_res = self.client.post(self.register_url, self.valid_payload, format='json')
        access_token = login_res.cookies['onfresh_access_token'].value

        client2 = APIClient()
        client2.cookies['onfresh_access_token'] = access_token
        res = client2.get(self.me_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['user']['email'], 'kavitha@nairbakery.in')

    def test_me_unauthenticated(self):
        res = self.client.get(self.me_url)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_clears_cookies(self):
        res = self.client.post(self.logout_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        # Verify cookies are deleted
        self.assertEqual(res.cookies['onfresh_access_token'].value, '')
        self.assertEqual(res.cookies['onfresh_refresh_token'].value, '')

    def test_token_refresh_via_cookie(self):
        login_res = self.client.post(self.register_url, self.valid_payload, format='json')
        refresh_token = login_res.cookies['onfresh_refresh_token'].value

        client2 = APIClient()
        client2.cookies['onfresh_refresh_token'] = refresh_token
        res = client2.post(self.refresh_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['status'], 'success')
        self.assertIn('onfresh_access_token', res.cookies)
        self.assertTrue(len(res.cookies['onfresh_access_token'].value) > 20)

    def test_token_refresh_via_body(self):
        login_res = self.client.post(self.register_url, self.valid_payload, format='json')
        refresh_token = login_res.cookies['onfresh_refresh_token'].value

        client2 = APIClient()
        res = client2.post(self.refresh_url, {'refresh': refresh_token}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['status'], 'success')
        self.assertIn('access', res.data)

