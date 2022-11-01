# Generated by Django 2.2.16 on 2021-10-15 14:53

import device.models.device
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('device', '0005_auto_20211001_1430'),
    ]

    operations = [
        migrations.AlterField(
            model_name='devicetype',
            name='name',
            field=models.CharField(choices=[('Home', 'Home'), ('Charge Controller', 'Charge Controller'), ('DELTA-RPI Inverter', 'DELTA-RPI Inverter'), ('WEATHER_STATION', 'WEATHER STATION'), ('SOLAR HYBRID INVERTER', 'SOLAR HYBRID INVERTER'), ('OTHER', 'OTHER')], help_text='Type name', max_length=50),
        ),
        migrations.CreateModel(
            name='Document',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('document', models.FileField(blank=True, null=True, upload_to=device.models.device.get_image_path)),
                ('description', models.CharField(blank=True, max_length=1024, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('device', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='device.Device')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
