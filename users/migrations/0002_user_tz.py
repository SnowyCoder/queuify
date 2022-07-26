# Generated by Django 4.0.5 on 2022-06-07 09:05

from django.db import migrations
import timezone_field.fields


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='tz',
            field=timezone_field.fields.TimeZoneField(choices_display='WITH_GMT_OFFSET', default='Europe/Rome'),
        ),
    ]
