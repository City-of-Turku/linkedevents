import logging
import operator
from functools import reduce

from django.contrib.postgres.search import SearchVector
from django.db import transaction
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.core.mail import send_mail
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django_orghierarchy.models import Organization
from events.models import Event, Place
from notifications.models import (NotificationType, NotificationTemplateException, render_notification_template)
from smtplib import SMTPException

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Place)
def place_post_save(sender, **kwargs):
    obj = kwargs["instance"]
    transaction.on_commit(populate_search_column(obj))


def date_updator(instance):
    try:
        # Mothers values need to be updated based on the min child start_time and max end_time date.
        ev_objs = Event.objects.filter(super_event_id=instance.super_event.id).iterator(chunk_size=10)
        '''
        child_list appends both start_time and end_time values from the above returned query (mothers all children).
        We can safely do this because logically, an end_time can never pre date a start_time. 
        Max will always be an end_time and respectively; minimum will always be a start_time.
        '''
        child_list = [v for x in ev_objs if x.deleted == False and x.event_status != 2 for v in (x.start_time, x.end_time)]
        
        if child_list:
            instance.super_event.start_time = min(child_list)
            instance.super_event.end_time = max(child_list)
            instance.super_event.save()
    except Exception as e:
        print(e)


def populate_search_column(obj):
    # Get the information of columns and weights to be added to search from the model.
    columns = {}
    columns["fi"] = obj.get_search_column_indexing("fi")
    columns["sv"] = obj.get_search_column_indexing("sv")
    columns["en"] = obj.get_search_column_indexing("en")
    id = obj.id

    def on_commit():
        search_vectors = {}
        for lang in ["fi", "sv", "en"]:
            search_vectors[lang] = []
            for column in columns[lang]:
                search_vectors[lang].append(
                    SearchVector(column[0], config=column[1], weight=column[2])
                )
            # Add all SearchVectors in search_vectors list to search_column.
            key = "search_column_%s" % lang
            obj.__class__.objects.filter(id=id).update(
                **{key: reduce(operator.add, search_vectors[lang])}
            )
    return on_commit


def post_update(instance, *args, **kwargs):
    if instance.sub_event_type == 'sub_recurring':
        date_updator(instance)


def post_save(instance, *args, **kwargs):
    try:
        if instance.sub_event_type == 'sub_recurring':
            if instance.start_time < instance.super_event.start_time:
                instance.super_event.start_time = instance.start_time             
            if instance.end_time > instance.super_event.end_time:
                instance.super_event.end_time = instance.end_time
            instance.super_event.save()
    except:
        pass


def post_delete(instance, *args, **kwargs):
    if instance.super_event_id:
        date_updator(instance)


def organization_post_save(sender, instance, created, **kwargs):
    if not created and instance.replaced_by:
        new_org = instance.replaced_by

        # copy old organization admin_users / regular_users to new organization
        new_org.admin_users.add(*list(instance.admin_users.all()))
        new_org.regular_users.add(*list(instance.regular_users.all()))

        # update owned systems to new owner
        instance.owned_systems.update(owner=new_org)


def user_post_save(sender, instance, created, **kwargs):
    if created:
        User = get_user_model()
        org = Organization.objects.get(id='yksilo:2000')
        org.private_users.add(instance)
        org.save()
        recipient_list = [item[0] for item in User.objects.filter(is_superuser=True).values_list('email')]
        notification_type = NotificationType.USER_CREATED
        context = {'user': instance}
        if len(recipient_list) == 0:
            logger.warning("No recipients for notification type '%s'" % notification_type, extra={'event': instance})
            return
        try:
            rendered_notification = render_notification_template(notification_type, context)
        except NotificationTemplateException as e:
            logger.error(e, exc_info=True)
            return
        try:
            send_mail(
                rendered_notification['subject'],
                rendered_notification['body'],
                'noreply@%s' % Site.objects.get_current().domain,
                recipient_list,
                html_message=rendered_notification['html_body']
            )
        except SMTPException as e:
            logger.error(e, exc_info=True, extra={'user': instance})
