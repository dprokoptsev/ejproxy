import datetime
import functools
import lxml.etree
import re
import requests

from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.conf import settings

from django.views.decorators.csrf import csrf_exempt

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


def forward(response):
    DISALLOWED_HEADERS = {
        "Date", "Server", "Keep-Alive", "Connection", "Transfer-Encoding"
    }
    ret = HttpResponse(status=response.status_code, content=response.content)
    for k, v in response.headers.items():
        if k in DISALLOWED_HEADERS:
            continue
        print(f"  - hdr: {k} = {v}")
        ret.headers[k] = v
    return ret


@csrf_exempt
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

    return forward(resp)


@csrf_exempt
def new_master(request):
    cookie = None
    if "user" in request.session:
        u = models.User.objects.filter(pk=request.session["user"])
        cookie = u[0].ej_cookie if u else None
    return forward(fetch(request, cookie=cookie))


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
            return forward(resp)

    login = fetch(request, url="/cgi-bin/new-master",
                  sid=user.ej_srvctl_sid, cookie=user.ej_cookie,
                  params={"action": 3, "contest_id": contest_id})
    if login.status_code == 302:
        sid = re.search(r"SID=([0-9a-f]+)", login.headers["Location"]).group(1)
        p = models.Participation(user=user, ej_contest_id=contest_id, ej_sid=sid)
        p.save()
    else:
        return HttpResponse(b"<h1>Forbidden</h1>", status=403)

    return forward(fetch(request, url="/cgi-bin/new-master",
                         sid=p.ej_sid, cookie=user.ej_cookie, params=params))


def index(request):
    return redirect("/cgi-bin/serve-control")


def contest(request, contest_id):
    return wrapped_new_master(request, contest_id)


def contest_run(request, contest_id, run_id):
    return wrapped_new_master(request, contest_id, action=36, run_id=run_id)


