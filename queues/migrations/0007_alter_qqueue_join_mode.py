# Generated by Django 4.0.5 on 2022-06-24 19:45

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('queues', '0006_qqueue_tz'),
    ]

    operations = [
        migrations.AlterField(
            model_name='qqueue',
            name='join_mode',
            field=models.CharField(choices=[('PUB', 'Public'), ('URL', 'URL only'), ('FRI', 'Friends only'), ('INV', 'Invite only')], default='INV', max_length=3),
        ),
    ]
