# Generated by Django 4.0.5 on 2022-06-07 08:52

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('queues', '0004_remove_qqueue_fixed_ticket_time_seconds_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='ticket',
            name='requested_time',
            field=models.DateTimeField(verbose_name='Requested time'),
            preserve_default=False,
        ),
        migrations.CreateModel(
            name='QueueOpenException',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('day', models.DateField(verbose_name='day')),
                ('from_time', models.TimeField(null=True, verbose_name='from')),
                ('to_time', models.TimeField(null=True, verbose_name='to')),
                ('queue', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='exc_schedule', to='queues.qqueue', verbose_name='queue')),
            ],
            options={
                'verbose_name': 'Opening range exception',
                'verbose_name_plural': 'Opening range exceptions',
            },
        ),
    ]