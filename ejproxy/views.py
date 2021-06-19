import datetime
import functools
import lxml.etree
import re
import requests
import urllib

from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.conf import settings
import django.urls

from django.middleware import csrf

from . import models



def static(request):
    resp = requests.get(f"{settings.EJUDGE_URL}/{request.get_full_path()}")
    ret = HttpResponse(status=resp.status_code, content=resp.content)
    ret.headers["Content-Type"] = resp.headers["Content-Type"]
    return ret


def fetch(request, *, sid=None, cookie=None, url=None, params=None):
    params = dict(params or {})
    if request.POST:
        params.update(request.POST)
    if sid:
        params["SID"] = sid

    cookies = {}
    if cookie:
        cookies["EJSID"] = cookie

    url = url or request.get_full_path()

    return requests.request(
        method=request.method,
        url=f"{settings.EJUDGE_URL}/{url}",
        headers={"Host": request.get_host()},
        allow_redirects=False,
        params=params,
        cookies=cookies,
    )


_forward_postprocessors = []
def forward_postprocessor(fn):
    _forward_postprocessors.append(fn)
    return fn


def forward(request, response):
    DISALLOWED_HEADERS = {
        "Date", "Server", "Keep-Alive", "Connection", "Transfer-Encoding",
        "Content-Length", "Set-Cookie",
    }
    content = response.content

    if response.headers["Content-Type"].startswith("text/html"):
        content = lxml.etree.fromstring(content, lxml.etree.HTMLParser())
        for p in _forward_postprocessors:
            p(request, content)
        content = lxml.etree.tostring(content)

    ret = HttpResponse(status=response.status_code, content=content)
    for k, v in response.headers.items():
        if k in DISALLOWED_HEADERS:
            continue
        ret.headers[k] = v
    return ret


@forward_postprocessor
def add_csrf_token(request, html):
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


@forward_postprocessor
def prettify_links(request, html):
    sid_to_contest_id = {}
    for a in html.xpath("//a[@href]"):
        url = urllib.parse.urlparse(a.attrib["href"])
        if not url.scheme.startswith("http"):
            continue

        params = dict(urllib.parse.parse_qsl(url.query))

        if url.path == "/cgi-bin/new-master" and params.get("action") == "3":
            a.attrib["href"] = django.urls.reverse(contest, kwargs={"contest_id": params["contest_id"]})
            continue

        if "SID" in params:
            p = models.Participation.objects.filter(ej_sid=params["SID"])
            if p:
                sid_to_contest_id[params["SID"]] = p[0].ej_contest_id

        if url.path == "/cgi-bin/new-master" and params.get("action") == "36":
            a.attrib["href"] = django.urls.reverse(contest_run, kwargs={
                "contest_id": sid_to_contest_id[params["SID"]],
                "run_id": params["run_id"]
            })


def serve_control(request):
    sid = cookie = None
    if "user" in request.session:
        u = models.User.objects.filter(pk=request.session["user"])
        if u:
            u = u[0]
            sid = u.ej_srvctl_sid
            cookie = u.ej_cookie

    resp = fetch(request, sid=sid, cookie=cookie)
    if (
        request.method == "POST" and
        "login" in request.POST and
        "password" in request.POST and
        resp.status_code == 302
    ):
        sid = re.search(r"SID=([0-9a-f]+)", resp.headers["Location"]).group(1)
        cookie = re.search(r"EJSID=([0-9a-f]+)", resp.headers["Set-Cookie"]).group(1)
        u, _ = models.User.objects.get_or_create(ej_srvctl_sid=sid, ej_cookie=cookie)
        u.save()
        request.session["user"] = u.id

        return_url = request.session.pop("return_url", None)
        if return_url:
            return redirect(return_url)

    return forward(request, resp)


def new_master(request):
    cookie = None
    if "user" in request.session:
        u = models.User.objects.filter(pk=request.session["user"])
        cookie = u[0].ej_cookie if u else None
    return forward(request, fetch(request, cookie=cookie))


def wrapped_new_master(request, contest_id, **params):
    user = None
    if "user" in request.session:
        users = models.User.objects.filter(pk=request.session["user"])
        if users:
            user = users[0]

    if not user:
        request.session["return_url"] = request.get_full_path()
        return redirect("/cgi-bin/serve-control")
    
    p = user.participation_set.filter(ej_contest_id=contest_id)
    if p:
        p = p[0]
        resp = fetch(request, url="/cgi-bin/new-master",
                     sid=p.ej_sid, cookie=user.ej_cookie, params=params)
        if resp.headers["Content-Type"].startswith("text/html"):
            html = lxml.etree.fromstring(resp.content, lxml.etree.HTMLParser())
            if html.xpath("//title")[0].text.endswith("Invalid session"):
                p.delete()
                p = None
        
        if p:
            return forward(request, resp)

    login = fetch(request, url="/cgi-bin/new-master",
                  sid=user.ej_srvctl_sid, cookie=user.ej_cookie,
                  params={"action": 3, "contest_id": contest_id})
    if login.status_code == 302:
        sid = re.search(r"SID=([0-9a-f]+)", login.headers["Location"]).group(1)
        p = models.Participation(user=user, ej_contest_id=contest_id, ej_sid=sid)
        p.save()
    else:
        return HttpResponse(b"<h1>Forbidden</h1>", status=403)

    return forward(request, fetch(request, url="/cgi-bin/new-master",
                         sid=p.ej_sid, cookie=user.ej_cookie, params=params))


def index(request):
    return redirect("/cgi-bin/serve-control")


def contest(request, contest_id):
    return wrapped_new_master(request, contest_id)


def contest_run(request, contest_id, run_id):
    return wrapped_new_master(request, contest_id, action=36, run_id=run_id)


