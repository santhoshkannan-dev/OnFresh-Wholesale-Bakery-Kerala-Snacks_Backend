from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from apps.customers.models import CustomerProfile, Address

User = get_user_model()


class CustomerProfileAndAddressTests(TestCase):
    def setUp(self):
        self.client1 = APIClient()
        self.user1 = User.objects.create_user(
            username='user1@store.in',
            email='user1@store.in',
            password='Password123!',
            first_name='Anand',
            last_name='Menon'
        )
        self.profile1 = CustomerProfile.objects.create(
            user=self.user1,
            business_name='Menon Provisions',
            business_type='retail_shop',
            contact_person='Anand Menon',
            phone_number='9846011223',
            gstin='32AAAAA0000A1Z5'
        )
        self.client1.force_authenticate(user=self.user1)

        # Second user
        self.client2 = APIClient()
        self.user2 = User.objects.create_user(
            username='user2@mart.in',
            email='user2@mart.in',
            password='Password123!',
            first_name='Rahul',
            last_name='Nair'
        )
        self.profile2 = CustomerProfile.objects.create(
            user=self.user2,
            business_name='Nair Supermart',
            business_type='supermarket',
            contact_person='Rahul Nair',
            phone_number='9846099887'
        )
        self.client2.force_authenticate(user=self.user2)

    def test_get_own_profile(self):
        res = self.client1.get('/api/customers/profile/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['profile']['business_name'], 'Menon Provisions')
        self.assertEqual(res.data['profile']['contact_person'], 'Anand Menon')
        self.assertEqual(res.data['profile']['email'], 'user1@store.in')

    def test_update_own_profile(self):
        res = self.client1.patch('/api/customers/profile/', {
            'business_name': 'Menon Wholesale Traders',
            'business_type': 'distributor',
            'full_name': 'Anand K. Menon'
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['profile']['business_name'], 'Menon Wholesale Traders')
        self.assertEqual(res.data['profile']['business_type'], 'distributor')

        # Check DB user name updated
        self.user1.refresh_from_db()
        self.assertEqual(self.user1.first_name, 'Anand')
        self.assertEqual(self.user1.last_name, 'K. Menon')

    def test_cannot_escalate_role_via_profile_patch(self):
        res = self.client1.patch('/api/customers/profile/', {
            'role': 'admin',
            'is_staff': True,
            'is_superuser': True
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.user1.refresh_from_db()
        self.assertFalse(self.user1.is_staff)
        self.assertFalse(self.user1.is_superuser)

    def test_valid_gstin_update(self):
        res = self.client1.patch('/api/customers/profile/', {
            'gstin': '32BBBBB1111B2Z6'
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.profile1.refresh_from_db()
        self.assertEqual(self.profile1.gstin, '32BBBBB1111B2Z6')

    def test_invalid_gstin_rejection(self):
        res = self.client1.patch('/api/customers/profile/', {
            'gstin': 'INVALID_GSTIN_123'
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('gstin', res.data['errors'])

    def test_address_creation_and_auto_default(self):
        res = self.client1.post('/api/customers/addresses/', {
            'address_type': 'shipping',
            'recipient_name': 'Menon Provisions Store',
            'phone_number': '9846011223',
            'address_line_1': 'Main Bazaar Road',
            'city': 'Vandiperiyar',
            'district': 'Idukki',
            'state': 'Kerala',
            'pincode': '685533',
            'is_default': False
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        # First address should be automatically set as default
        self.assertTrue(res.data['is_default'])

    def test_default_address_switch_behavior(self):
        # Create address 1
        addr1 = Address.objects.create(
            customer=self.profile1,
            address_type='shipping',
            recipient_name='Warehouse 1',
            phone_number='9846011223',
            address_line_1='Road 1',
            city='Vandiperiyar',
            district='Idukki',
            pincode='685533',
            is_default=True
        )

        # Create address 2 as default
        res2 = self.client1.post('/api/customers/addresses/', {
            'address_type': 'shipping',
            'recipient_name': 'Warehouse 2',
            'phone_number': '9846011223',
            'address_line_1': 'Road 2',
            'city': 'Kumily',
            'district': 'Idukki',
            'state': 'Kerala',
            'pincode': '685509',
            'is_default': True
        }, format='json')
        self.assertEqual(res2.status_code, status.HTTP_201_CREATED)
        self.assertTrue(res2.data['is_default'])

        # addr1 should now have is_default = False
        addr1.refresh_from_db()
        self.assertFalse(addr1.is_default)

    def test_address_isolation_between_customers(self):
        # User 1 creates address
        addr1 = Address.objects.create(
            customer=self.profile1,
            address_type='shipping',
            recipient_name='Secret Location 1',
            phone_number='9846011223',
            address_line_1='Confidential Lane',
            city='Vandiperiyar',
            district='Idukki',
            pincode='685533',
            is_default=True
        )

        # User 2 tries to GET user 1's address
        res_get = self.client2.get(f'/api/customers/addresses/{addr1.id}/')
        self.assertEqual(res_get.status_code, status.HTTP_404_NOT_FOUND)

        # User 2 tries to PATCH user 1's address
        res_patch = self.client2.patch(f'/api/customers/addresses/{addr1.id}/', {
            'recipient_name': 'Hacked Recipient'
        }, format='json')
        self.assertEqual(res_patch.status_code, status.HTTP_404_NOT_FOUND)

        # User 2 tries to DELETE user 1's address
        res_del = self.client2.delete(f'/api/customers/addresses/{addr1.id}/')
        self.assertEqual(res_del.status_code, status.HTTP_404_NOT_FOUND)

        # Ensure addr1 was NOT changed in DB
        addr1.refresh_from_db()
        self.assertEqual(addr1.recipient_name, 'Secret Location 1')

    def test_unauthenticated_requests_blocked(self):
        anon_client = APIClient()
        res_profile = anon_client.get('/api/customers/profile/')
        self.assertEqual(res_profile.status_code, status.HTTP_401_UNAUTHORIZED)

        res_addr = anon_client.get('/api/customers/addresses/')
        self.assertEqual(res_addr.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_individual_registration_profile_defaults(self):
        client = APIClient()
        res = client.post('/api/auth/register/', {
            'full_name': 'Asha Joseph',
            'email': 'asha@gmail.com',
            'mobile_number': '9846123456',
            'customer_type': 'individual',
            'password': 'SecureRetailPass123!',
            'password_confirmation': 'SecureRetailPass123!',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email='asha@gmail.com')
        self.assertEqual(user.customer_profile.customer_type, 'individual')
        self.assertEqual(user.customer_profile.wholesale_status, 'none')
        self.assertFalse(user.customer_profile.is_wholesale_approved)

    def test_business_registration_wholesale_pending(self):
        client = APIClient()
        res = client.post('/api/auth/register/', {
            'full_name': 'Kannan Pillai',
            'email': 'kannan@kannanbakery.com',
            'mobile_number': '9846987654',
            'customer_type': 'business',
            'business_name': 'Kannan Sweets & Bakery',
            'business_type': 'bakery',
            'gstin': '32AAAAA0000A1Z5',
            'password': 'SecureBusinessPass123!',
            'password_confirmation': 'SecureBusinessPass123!',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email='kannan@kannanbakery.com')
        self.assertEqual(user.customer_profile.customer_type, 'business')
        self.assertEqual(user.customer_profile.wholesale_status, 'pending')
        self.assertFalse(user.customer_profile.is_wholesale_approved)

    def test_business_registration_requires_business_name(self):
        client = APIClient()
        res = client.post('/api/auth/register/', {
            'full_name': 'Faulty Business User',
            'email': 'faulty@business.com',
            'mobile_number': '9846999999',
            'customer_type': 'business',
            'business_name': '',  # Empty
            'password': 'SecurePass123!',
            'password_confirmation': 'SecurePass123!',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('business_name', res.data['errors'])

    def test_individual_upgrade_to_wholesale_request(self):
        # User 1 is currently individual or requests wholesale
        res = self.client1.post('/api/customers/request-wholesale/', {
            'business_name': 'Menon Wholesale Trading Co',
            'business_type': 'distributor',
            'contact_person': 'Anand Menon',
            'phone_number': '9846011223',
            'gstin': '32AAAAA0000A1Z5',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.profile1.refresh_from_db()
        self.assertEqual(self.profile1.customer_type, 'business')
        self.assertEqual(self.profile1.wholesale_status, 'pending')
        self.assertEqual(self.profile1.business_name, 'Menon Wholesale Trading Co')
        self.assertFalse(self.profile1.is_wholesale_approved)

        # Admin approves
        self.profile1.wholesale_status = 'approved'
        self.profile1.save()
        self.assertTrue(self.profile1.is_wholesale_approved)

    def test_admin_wholesale_applications_list_and_decision(self):
        # Create staff user
        staff_user = User.objects.create_user(
            username='staff@onfresh.test',
            email='staff@onfresh.test',
            password='StaffPassword123!',
            is_staff=True
        )
        staff_client = APIClient()
        staff_client.force_authenticate(user=staff_user)

        # Set user 2 to pending
        self.profile2.customer_type = 'business'
        self.profile2.wholesale_status = 'pending'
        self.profile2.save()

        # 1. Staff lists applications
        res_list = staff_client.get('/api/customers/admin/applications/?status=pending')
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(res_list.data['applications']), 1)

        # 2. Staff approves user 2
        res_approve = staff_client.post(
            f'/api/customers/admin/applications/{self.profile2.id}/decision/',
            {'action': 'approve'},
            format='json'
        )
        self.assertEqual(res_approve.status_code, status.HTTP_200_OK)
        self.profile2.refresh_from_db()
        self.assertTrue(self.profile2.is_wholesale_approved)
        self.assertEqual(self.profile2.wholesale_status, 'approved')

        # 3. Staff rejects user 1 with reason
        res_reject = staff_client.post(
            f'/api/customers/admin/applications/{self.profile1.id}/decision/',
            {'action': 'reject', 'reason': 'Business registration document invalid.'},
            format='json'
        )
        self.assertEqual(res_reject.status_code, status.HTTP_200_OK)
        self.profile1.refresh_from_db()
        self.assertFalse(self.profile1.is_wholesale_approved)
        self.assertEqual(self.profile1.wholesale_status, 'rejected')
        self.assertEqual(self.profile1.rejection_reason, 'Business registration document invalid.')

    def test_non_staff_forbidden_from_admin_wholesale_endpoints(self):
        # Customer 1 attempts to list admin applications
        res = self.client1.get('/api/customers/admin/applications/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Customer 1 attempts to approve own profile
        res_post = self.client1.post(
            f'/api/customers/admin/applications/{self.profile1.id}/decision/',
            {'action': 'approve'},
            format='json'
        )
        self.assertEqual(res_post.status_code, status.HTTP_403_FORBIDDEN)

