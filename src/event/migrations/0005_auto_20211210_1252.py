# Generated by Django 2.2.16 on 2021-12-10 12:52

import django.contrib.postgres.fields.jsonb
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('event', '0004_auto_20211207_1558'),
    ]

    operations = [
        migrations.AddField(
            model_name='eventhistory',
            name='action',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='event.Action'),
        ),
        migrations.AddField(
            model_name='eventhistory',
            name='result',
            field=django.contrib.postgres.fields.jsonb.JSONField(blank=True, null=True),
        ),
    ]
