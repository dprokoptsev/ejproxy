from django.db import models

class User(models.Model):
    ej_srvctl_sid = models.CharField(max_length=64, null=True)
    ej_cookie = models.CharField(max_length=64, null=True)

class Participation(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_index=True)
    ej_contest_id = models.IntegerField(db_index=True)
    ej_sid = models.CharField(max_length=64, null=True)
