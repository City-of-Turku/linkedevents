from unittest.mock import MagicMock

from django.test import TestCase
from django_orghierarchy.models import Organization

from ..models import DataSource, Event, PublicationStatus
from ..permissions import UserModelPermissionMixin
from helevents.models import User


class TestUserModelPermissionMixin(TestCase):

    def setUp(self):
        self.instance = UserModelPermissionMixin()

        self.data_source = DataSource.objects.create(
            id='ds',
            name='data-source',
            api_key="test_api_key",
            user_editable=True,
        )
        self.org = Organization.objects.create(
            name='org',
            origin_id='org',
            data_source=self.data_source,
        )

    def test_is_admin(self):
        self.assertRaises(
            NotImplementedError,
            self.instance.is_admin,
            self.org,
        )

    def test_is_regular_user(self):
        self.assertRaises(
            NotImplementedError,
            self.instance.is_regular_user,
            self.org,
        )

    def test_is_private_user(self):
        self.assertRaises(
            NotImplementedError,
            self.instance.is_private_user,
            self.org,
        )

    def test_can_edit_event(self):
        # test for admin user
        self.instance.is_admin = MagicMock(return_value=True)

        can_edit = self.instance.can_edit_event(self.org, PublicationStatus.PUBLIC)
        self.assertTrue(can_edit)
        can_edit = self.instance.can_edit_event(self.org, PublicationStatus.DRAFT)
        self.assertTrue(can_edit)

        # test for private user
        self.instance.is_admin = MagicMock(return_value=False)
        self.instance.is_regular_user = MagicMock(return_value=False)
        self.instance.is_private_user = MagicMock(return_value=True)

        can_edit = self.instance.can_edit_event(self.org, PublicationStatus.PUBLIC)
        self.assertFalse(can_edit)
        can_edit = self.instance.can_edit_event(self.org, PublicationStatus.DRAFT)
        self.assertTrue(can_edit)

        # test for other users
        self.instance.is_admin = MagicMock(return_value=False)
        self.instance.is_regular_user = MagicMock(return_value=False)
        self.instance.is_private_user = MagicMock(return_value=False)

        can_edit = self.instance.can_edit_event(self.org, PublicationStatus.PUBLIC)
        self.assertFalse(can_edit)
        can_edit = self.instance.can_edit_event(self.org, PublicationStatus.DRAFT)
        self.assertFalse(can_edit)


class TestUserModelPermissions(TestCase):

    def setUp(self):
        self.instance = User.objects.create()

        self.data_source = DataSource.objects.create(
            id='ds',
            name='data-source',
            api_key="test_api_key",
            user_editable=True,
        )
        self.org = Organization.objects.create(
            name='org',
            origin_id='org',
            data_source=self.data_source,
        )
        self.org2 = Organization.objects.create(
            name='org2',
            origin_id='org2',
            data_source=self.data_source,
            parent=self.org
        )
        self.org3 = Organization.objects.create(
            name='org3',
            origin_id='org3',
            data_source=self.data_source,
        )

    def test_get_editable_events(self):
        # this test requires the whole User model, as admin organizations are dependent on org hierarchy
        event_1 = Event.objects.create(
            id='event-1',
            name='event-1',
            data_source=self.data_source,
            publisher=self.org,
            publication_status=PublicationStatus.PUBLIC,
        )
        event_2 = Event.objects.create(
            id='event-2',
            name='event-2',
            data_source=self.data_source,
            publisher=self.org,
            publication_status=PublicationStatus.DRAFT,
        )

        # admins should be allowed to see and edit suborg events
        event_3 = Event.objects.create(
            id='event-3',
            name='event-3',
            data_source=self.data_source,
            publisher=self.org2,
            publication_status=PublicationStatus.DRAFT
        )

        # superusers should be allowed to see events from all organizations
        event_4 = Event.objects.create(
            id='event-4',
            name='event-4',
            data_source=self.data_source,
            publisher=self.org3,
            publication_status=PublicationStatus.DRAFT
        )

        total_qs = Event.objects.all()
        # test for admin user
        # magicmock cannot be used for object properties
        self.instance.admin_organizations.add(self.org)
        qs = self.instance.get_editable_events(total_qs)
        self.assertQuerysetEqual(qs, values=[repr(event_1), repr(event_2), repr(event_3)], transform=repr, ordered=False)

        # test for regular user
        self.instance.admin_organizations.remove(self.org)
        self.instance.organization_memberships.add(self.org)
        qs = self.instance.get_editable_events(total_qs)
        self.assertQuerysetEqual(qs, values=[repr(event_2)], transform=repr)

        # test for private user
        self.instance.organization_memberships.remove(self.org)
        self.instance.public_memberships.add(self.org)
        qs = self.instance.get_editable_events(total_qs)
        self.assertQuerysetEqual(qs, values=[repr(event_1)], transform=repr)

        # test for other users
        self.instance.public_memberships.remove(self.org)
        qs = self.instance.get_editable_events(total_qs)
        self.assertQuerysetEqual(qs, [])

        # test for superusers
        self.instance.is_superuser = True
        qs = self.instance.get_editable_events(total_qs)
        self.assertQuerysetEqual(
            qs,
            values=[repr(event_1), repr(event_2), repr(event_3), repr(event_4)],
            transform=repr,
            ordered=False,
        )

    def test_superuser_can_edit_events(self):
        self.instance.is_superuser = True
        can_edit = self.instance.can_edit_event(self.org, PublicationStatus.PUBLIC)
        self.assertTrue(can_edit)
        can_edit = self.instance.can_edit_event(self.org, PublicationStatus.DRAFT)
        self.assertTrue(can_edit)
