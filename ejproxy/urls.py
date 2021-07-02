from django.urls import include, path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('login', views.login, name='login'),
    path('c<int:contest_id>', views.contest, name='contest'),
    path('c<int:contest_id>/r<int:run_id>', views.contest_run, name='contest_run'),
]
