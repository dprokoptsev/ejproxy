import datetime
import functools
import lxml.etree
import urllib

from django.middleware import csrf
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render, redirect
from django.conf import settings
from django import urls

from . import ejudge
from . import models


@ejudge.postprocessor
def inject_csrf_token(request, html):
    token = None
    for form in html.xpath("//form[@method='post']"):
        if not len(form.getchildren()):
            continue
        if token is None:
            token = csrf.get_token(request)
        elt = lxml.etree.Element("input")
        elt.attrib["type"] = "hidden"
        elt.attrib["name"] = "csrfmiddlewaretoken"
        elt.attrib["value"] = token
        form.getchildren()[0].addprevious(elt)


@ejudge.postprocessor
def capture_login(request, html):
    for form in html.xpath("//form"):
        if (form.xpath("descendant::input[@name='login']") and
            form.xpath("descendant::input[@name='password']") and
            form.attrib["action"].endswith("/cgi-bin/serve-control")
        ):
            form.attrib["action"] = urls.reverse(login)


@ejudge.postprocessor
def prettify_links(request, html):
    sid_to_contest_id = {}
    for a in html.xpath("//a[@href]"):
        url = urllib.parse.urlparse(a.attrib["href"])
        if not url.scheme.startswith("http"):
            continue
        params = dict(urllib.parse.parse_qsl(url.query))

        if url.path == "/cgi-bin/new-master" and params.get("action") == "3":
            a.attrib["href"] = urls.reverse(contest, kwargs={"contest_id": params["contest_id"]})
            continue

        if "SID" in params and params["SID"] not in sid_to_contest_id:
            p = models.Participation.objects.filter(ej_sid=params["SID"])
            if p:
                sid_to_contest_id[params["SID"]] = p[0].ej_contest_id
            else:
                continue

        if url.path == "/cgi-bin/new-master" and params.get("action") == "36":
            a.attrib["href"] = urls.reverse(contest_run, kwargs={
                "contest_id": sid_to_contest_id[params["SID"]],
                "run_id": params["run_id"],
            })
        elif url.path == "/cgi-bin/new-master" and params.get("action") == "2":
            a.attrib["href"] = urls.reverse(contest, kwargs={
                "contest_id": sid_to_contest_id[params["SID"]]
            })


def require_user(fn):
    @functools.wraps(fn)
    def wrap(request, *args, **kwargs):
        sid = ejudge.srvctl_sid(request)
        if not sid:
            request.session["return_url"] = request.path
            return ejudge.forward(request, "serve-control")
        kwargs["user"] = models.User.objects.get(ej_srvctl_sid=sid)
        return fn(request, *args, **kwargs)
    return wrap


@require_user
def index(request, user):
    return ejudge.forward(request, "serve-control", SID=user.ej_srvctl_sid)


def login(request):
    login = request.POST["login"]
    password = request.POST["password"]
    if not login or not password:
        return ejudge.forward(request, "serve-control")

    sid, cookie = ejudge.login(request, login, password)
    if sid is None:
        # TODO: inject "Bad login/password message" here
        return ejudge.forward(request, "serve-control")

    user, _ = models.User.objects.get_or_create(ej_srvctl_sid=sid)
    user.save()

    request.session["ej_master_sid"] = sid
    return_url = request.session.pop("return_url", urls.reverse(index))
    ret = redirect(return_url)
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
        if sid:
            p = models.Participation(user=user, ej_contest_id=contest_id, ej_sid=sid)
            p.save()
    return p

@require_user
def contest(request, user, contest_id):
    p = get_participation(request, user, contest_id)
    if not p:
        return HttpResponseForbidden()
    return ejudge.forward(request, "new-master", SID=p.ej_sid)


@require_user
def contest_run(request, user, contest_id, run_id):
    p = get_participation(request, user, contest_id)
    if not p:
        return HttpResponseForbidden()
    return ejudge.forward(request, "new-master", SID=p.ej_sid, action=36, run_id=run_id)

