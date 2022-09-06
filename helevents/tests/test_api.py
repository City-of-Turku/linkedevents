from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from django_orghierarchy.models import Organization
from events.models import DataSource
from events.tests.utils import versioned_reverse as reverse

class UserApiTests(APITestCase):

    def setUp(self):
        user_model = get_user_model()
        
        data_source = DataSource.objects.create(
            id='ds',
            name='data-source',
        )
        data_source_yksilo = DataSource.objects.create(
            id='yksilo',
            name='yksilo',
        )
        self.org_private_users = Organization.objects.create(
            name='yksilo',
            origin_id='2000',
            data_source=data_source_yksilo,
        )
        self.org_1 = Organization.objects.create(
            name='org-1',
            origin_id='org-1',
            data_source=data_source,
        )
        self.org_2 = Organization.objects.create(
            name='org-2',
            origin_id='org-2',
            data_source=data_source,
        )
        self.user_1 = user_model.objects.create(
            username='user_1',
            first_name='Test1',
            last_name='Tester1',
            email='test1@tester1.com',
        )
        self.user_2 = user_model.objects.create(
            username='user_2',
            first_name='Test2',
            last_name='Tester2',
            email='test2@tester2.com',
        )
        self.superuser = user_model.objects.create(
            username='super_user',
            first_name='Super',
            last_name='Tester',
            email='super@tester.com',
            is_superuser=True,
        )


    def test_update_organization_levels_raises_401_for_unauthenticated_users(self):
        '''Tests that anon users cannot update org levels'''
        url = reverse('user-detail', kwargs={'pk': self.user_1.username}) + 'update_organization_levels/'
        data = {'test': 1}
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


    def test_update_organization_levels_raises_403_for_normal_users(self):
        '''Tests that users without org perms cannot update org levels'''
        url = reverse('user-detail', kwargs={'pk': self.user_1.username}) + 'update_organization_levels/'
        data = {
            'organization': self.org_1.id,
            'organization_levels': {'admin': True, 'regular': False, 'private': False}
        }
        self.client.force_authenticate(self.user_1)
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


    def test_update_organization_levels_raises_403_for_admin_not_in_given_org(self):
        '''Tests that admin users for other than target organization cannot update org levels'''
        url = reverse('user-detail', kwargs={'pk': self.user_1.username}) + 'update_organization_levels/'
        data = {
            'organization': self.org_1.id,
            'organization_levels': {'admin': True, 'regular': False, 'private': False}
        }
        self.org_2.admin_users.add(self.user_2)
        self.client.force_authenticate(self.user_2)
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


    def test_update_organization_levels_raises_403_for_regular_user(self):
        '''Tests that regular users in organization cannot update org levels'''
        url = reverse('user-detail', kwargs={'pk': self.user_1.username}) + 'update_organization_levels/'
        data = {
            'organization': self.org_1.id,
            'organization_levels': {'admin': True, 'regular': False, 'private': False}
        }
        self.org_1.regular_users.add(self.user_2)
        self.client.force_authenticate(self.user_2)
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


    def test_update_organization_levels_success_for_superuser(self):
        '''Tests that superusers can update org levels'''
        url = reverse('user-detail', kwargs={'pk': self.user_1.username}) + 'update_organization_levels/'
        data = {
            'organization': self.org_1.id,
            'organization_levels': {'admin': True, 'regular': False, 'private': False}
        }
        self.client.force_authenticate(self.superuser)
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


    def test_update_organization_levels_success_for_organization_admin(self):
        '''Tests that admin users of target organization can update org levels'''
        url = reverse('user-detail', kwargs={'pk': self.user_1.username}) + 'update_organization_levels/'
        data = {
            'organization': self.org_1.id,
            'organization_levels': {'admin': True, 'regular': False, 'private': False}
        }
        self.org_1.admin_users.add(self.user_2)
        self.client.force_authenticate(self.user_2)
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


    def test_update_organization_levels_raises_400_when_given_org_is_invalid_or_missing(self):
        '''Tests that organization in request payload is validated correctly'''
        url = reverse('user-detail', kwargs={'pk': self.user_1.username}) + 'update_organization_levels/'
        data = {
            'organization_levels': {'admin': True, 'regular': False, 'private': False}
        }
        self.client.force_authenticate(self.superuser)
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data.update({'organization': 'wrong-id'})
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


    def test_update_organization_levels_raises_400_when_given_org_levels_is_invalid_or_missing(self):
        '''Tests that organization levels in request payload is validated correctly'''
        url = reverse('user-detail', kwargs={'pk': self.user_1.username}) + 'update_organization_levels/'
        data = {'organization': self.org_1.id}
        self.client.force_authenticate(self.superuser)
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        data.update({'organization_levels': 'wrong-type'})
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        data.update({'organization_levels': {'admin': True, 'regular': False}})
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        data.update({'organization_levels': {'admin': 1, 'regular': False, 'private': False}})
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


    def test_get_users_raises_401_for_anon_user(self):
        '''Tests that anon users cannot use user endpoint'''
        url = reverse('user-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


    def test_get_users_returns_normal_users_own_data(self):
        '''Tests that authenticated users get their own user data'''
        url = reverse('user-list')
        self.client.force_authenticate(self.user_1)
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data.get('data')
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0].get('username'), self.user_1.username)


    def test_get_users_returns_all_users_for_superusers(self):
        '''Tests that superusers get all user data'''
        url = reverse('user-list')
        self.client.force_authenticate(self.superuser)
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data.get('data')
        self.assertEqual(len(data), 3) # user1, user2 and superuser


    def test_get_users_returns_admin_users_own_data(self):
        '''Tests that admins in organizations get their own user data'''
        url = reverse('user-list')
        self.org_1.admin_users.add(self.user_1)
        self.client.force_authenticate(self.user_1)
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data.get('data')
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0].get('username'), self.user_1.username)


    def test_get_users_email_filtered_does_not_return_other_users_for_normal_users(self):
        '''Tests that normal users without permissions cannot filter users with email'''
        url = reverse('user-list') + f'?email={self.user_2.email}'
        self.client.force_authenticate(self.user_1)
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data.get('data')
        self.assertEqual(len(data), 0)


    def test_get_users_email_filtered_returns_correct_user_data_for_superusers(self):
        '''Tests that superusers can filter users with email'''
        url = reverse('user-list') + f'?email={self.user_2.email}'
        self.client.force_authenticate(self.superuser)
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data.get('data')
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0].get('username'), self.user_2.username)


    def test_get_users_email_filtered_returns_correct_user_data_for_admins(self):
        '''Tests that organization admins can filter users with email'''
        url = reverse('user-list') + f'?email={self.user_2.email}'
        self.org_1.admin_users.add(self.user_1)
        self.client.force_authenticate(self.user_1)
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data.get('data')
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0].get('username'), self.user_2.username)
