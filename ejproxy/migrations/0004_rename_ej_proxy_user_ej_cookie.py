# Generated by Django 3.2.4 on 2021-06-18 11:00

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('ejproxy', '0003_user_ej_proxy'),
    ]

    operations = [
        migrations.RenameField(
            model_name='user',
            old_name='ej_proxy',
            new_name='ej_cookie',
        ),
    ]
