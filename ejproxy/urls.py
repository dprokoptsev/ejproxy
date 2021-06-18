from django.urls import include, path, re_path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('c<int:contest_id>', views.contest, name='contest'),
    path('c<int:contest_id>/r<int:run_id>', views.contest_run, name='contest_run'),

    re_path(r'^ejudge/.*', views.static, name='static'),
    path('cgi-bin/serve-control', views.serve_control, name='serve_control'),
    path('cgi-bin/new-master', views.new_master, name='new_master'),
]
