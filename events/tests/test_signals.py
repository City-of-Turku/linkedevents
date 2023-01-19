from django.contrib.auth import get_user_model
from django.test import TestCase
from django_orghierarchy.models import Organization

from ..models import DataSource


class TestOrganizationPostSave(TestCase):

    def setUp(self):
        user_model = get_user_model()
        self.user_1 = user_model.objects.create(username='user-1')
        self.user_2 = user_model.objects.create(username='user-2')

        self.data_source_1 = DataSource.objects.create(
            id='ds-1',
            name='data-source-1',
        )
        self.data_source_2 = DataSource.objects.create(
            id='ds-2',
            name='data-source-2'
        )
        self.org_1 = Organization.objects.create(
            data_source=self.data_source_1,
            name='org-1',
            origin_id='org-1',
        )
        self.org_2 = Organization.objects.create(
            data_source=self.data_source_2,
            name='org-2',
            origin_id='org-2',
        )
        self.data_source_1.owner = self.org_1
        self.data_source_1.save()
        self.data_source_2.owner = self.org_2
        self.data_source_2.save()

        self.org_1.admin_users.set([self.user_1, self.user_2])
        self.org_1.regular_users.set([self.user_1, self.user_2])

    def test_organization_post_save(self):
        self.org_1.replaced_by = self.org_2
        self.org_1.save()

        qs = self.org_2.admin_users.all()
        self.assertQuerysetEqual(qs, values=[repr(self.user_1), repr(self.user_2)], transform=repr, ordered=False)

        qs = self.org_2.regular_users.all()
        self.assertQuerysetEqual(qs, values=[repr(self.user_1), repr(self.user_2)], transform=repr, ordered=False)

        self.data_source_1.refresh_from_db()
        self.assertEqual(self.data_source_1.owner, self.org_2)


    def test_user_post_save_auto_private_organization_addition_not_in_use(self):
        '''
        Tests that user is not added to private organization when settings dont allow it
        '''
        data_source_yksilo = DataSource.objects.create(
            id='yksilo',
            name='yksilo',
        )
        Organization.objects.create(
            data_source=data_source_yksilo,
            name='yksilo',
            origin_id='2000',
        )
        with self.settings(ADD_USERS_TO_PRIVATE_ORG_AUTOMATICALLY=False):
            new_user_1 = get_user_model().objects.create(username='new-user-1')
            qs = new_user_1.public_memberships.all()
            self.assertQuerysetEqual(qs, [])

    
    def test_user_post_save_auto_private_organization_addition_in_use(self):
        '''
        Tests that user is added to private organization when settings allow it
        '''
        data_source_yksilo = DataSource.objects.create(
            id='yksilo',
            name='yksilo',
        )
        private_org = Organization.objects.create(
            data_source=data_source_yksilo,
            name='yksilo',
            origin_id='2000',
        )
        with self.settings(ADD_USERS_TO_PRIVATE_ORG_AUTOMATICALLY=True):
            new_user_1 = get_user_model().objects.create(username='new-user-1')
            qs = new_user_1.public_memberships.all()
            self.assertQuerysetEqual(qs, values=[repr(private_org)], transform=repr)
