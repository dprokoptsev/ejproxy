# Generated by Django 3.2.4 on 2021-06-18 10:57

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ejproxy', '0002_auto_20210618_0302'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='ej_proxy',
            field=models.CharField(max_length=64, null=True),
        ),
    ]