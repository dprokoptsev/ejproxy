from django.urls import include, path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('login', views.login, name='login'),
    path('contest/<int:contest_id>', views.contest, name='contest'),
    path('contest/<int:contest_id>/run/<int:run_id>', views.contest_run, name='contest_run'),
]
