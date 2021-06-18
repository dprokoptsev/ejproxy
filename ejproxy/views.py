import datetime
import functools

from django.http import HttpResponse
from django.shortcuts import render, redirect

from . import ejudge
from . import models

EJUDGE_PREFIX = "http://ejudgetest/cgi-bin"


def require_user(fn):
    @functools.wraps(fn)
    def wrap(request, *args, **kwargs):
        sid = ejudge.srvctl_sid(request)
        if not sid:
            return render(request, "login.html", {"return_uri": request.path})
        kwargs["user"] = models.User.objects.get(ej_srvctl_sid=sid)
        return fn(request, *args, **kwargs)
    return wrap


@require_user
def index(request, user):
    return redirect(f"{EJUDGE_PREFIX}/serve-control?SID={user.ej_srvctl_sid}")


def login(request):
    login = request.POST["login"]
    password = request.POST["password"]
    return_uri = request.POST["return_uri"] or "/"
    if not login or not password:
        return render(request, "login.html", {"return_uri": return_uri})

    sid, cookie = ejudge.login(request, login, password)
    if sid is None:
        return render(request, "login.html", {"return_uri": return_uri, "message": "Invalid credentials"})

    user, _ = models.User.objects.get_or_create(ej_srvctl_sid=sid)
    user.save()

    request.session["ej_master_sid"] = sid
    ret = redirect(return_uri)
    ret.set_cookie("EJSID", cookie, expires=datetime.datetime.now() + datetime.timedelta(365, 0))
    return ret


def get_participation(request, user, contest_id):
    p = user.participation_set.filter(ej_contest_id=contest_id)
    if p:
        p = p[0]
        if not ejudge.contest_sid_valid(request, p.ej_sid):
            p.delete()
            p = None

    if not p:
        sid = ejudge.contest_login(request, contest_id)
        p = models.Participation(user=user, ej_contest_id=contest_id, ej_sid=sid)
        p.save()
    return p

@require_user
def contest(request, user, contest_id):
    p = get_participation(request, user, contest_id)
    return redirect(f"{EJUDGE_PREFIX}/new-master?SID={p.ej_sid}")


@require_user
def contest_run(request, user, contest_id, run_id):
    p = get_participation(request, user, contest_id)
    return redirect(f"{EJUDGE_PREFIX}/new-master?SID={p.ej_sid}&action=36&run_id={run_id}")


