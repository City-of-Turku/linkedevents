import logging

from django.core.mail import send_mail
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from events.models import Event
from notifications.models import (NotificationType, NotificationTemplateException, render_notification_template)
from smtplib import SMTPException

logger = logging.getLogger(__name__)

def post_update(instance, *args, **kwargs):
    try:
        if instance.sub_event_type == 'sub_recurring':
            try:
                ev_objs = Event.objects.filter(super_event_id=instance.super_event.id)
                #child_start_times = [x.start_time for x in ev_objs]
                #child_end_times = [x.end_time for x in ev_objs]
                child_list = [x for x in (ev_objs.start_time, ev_objs.end_time)]

                instance.super_event.start_time = min(child_list)
                instance.super_event.end_time = max(child_list)
                #instance.super_event.start_time = min(child_start_times)
                #instance.super_event.end_time = max(child_start_times)
                instance.super_event.save()
            except Exception as e:
                print(e)
                pass

            #if instance.start_time < instance.super_event.start_time:
            #    instance.super_event.start_time = instance.start_time             
            #if instance.end_time > instance.super_event.end_time:
            #    instance.super_event.end_time = instance.end_time

            #instance.super_event.save()
    except:
        pass

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
