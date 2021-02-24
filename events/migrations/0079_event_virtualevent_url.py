# Generated by Django 2.2.11 on 2021-01-14 07:55

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0078_event_is_virtualevent'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='virtualevent_url',
            field=models.URLField(blank=True, max_length=1000, null=True, verbose_name='Virtual event location'),
        ),
    ]
