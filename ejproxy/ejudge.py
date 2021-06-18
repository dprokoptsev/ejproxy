import io
import subprocess
import urllib.parse
import lxml.etree
import re

CGI_ROOT = "/opt/ejudge/libexec/ejudge/cgi-bin"

def _runcgi(request, handle, method="GET", **query_params):
    query_string = urllib.parse.urlencode(query_params)
    env = {
        "REMOTE_ADDR": request.META["REMOTE_ADDR"],
        "SCRIPT_NAME": f"/cgi-bin/{handle}",
        "REQUEST_METHOD": method
    }
    if "EJSID" in request.COOKIES:
        env["HTTP_COOKIE"] = f"EJSID={request.COOKIES['EJSID']}"

    if method == "POST":
        stdin = query_string
        env["CONTENT_LENGTH"] = str(len(stdin))
        env["CONTENT_TYPE"] = "application/x-www-form-urlencoded"
    else:
        env["QUERY_STRING"] = query_string
        stdin = None

    result = subprocess.run(
        f"{CGI_ROOT}/{handle}",
        input=stdin,
        capture_output=True,
        check=True,
        encoding="utf-8",
        env=env
    )

    hdr = {}
    body = io.StringIO()
    mode = "header"
    for line in result.stdout.split("\n"):
        if line.strip() == "" and mode == "header":
            mode = "body"
        elif mode == "header":
            k, v = line.split(": ")
            hdr[k] = v
        else:
            print(line, file=body)

    return (hdr, lxml.etree.fromstring(body.getvalue(), lxml.etree.HTMLParser()))


def _xpath(html, xp):
    elem = html.xpath(xp)
    return elem[0] if len(elem) else None


def _breakdown_url(url):
    return dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
    

def login(request, login, password):
    """Logs in to ejudge serve-control.
    Returns a pair (SID, cookie) on successful login, or (None, None) otherwise.
    """
    hdrs, resp = _runcgi(request, "serve-control", method="POST", login=login, password=password)
    if _xpath(resp, "//title/text()") == "Invalid login":
        return (None, None)
    else:
        sid = _breakdown_url(hdrs["Location"])["SID"]
        m = re.match("EJSID=([0-9a-f]+)(;.*)?$", hdrs["Set-Cookie"])
        assert m is not None
        print(f"SID={sid}, cookie={m.group(1)}")
        return (sid, m.group(1))


def srvctl_sid(request):
    sid = request.session.get("ej_master_sid", "")
    if not sid:
        return None

    _, resp = _runcgi(request, "serve-control", SID=sid)
    return sid if _xpath(resp, "//input[@name='login']") is None else None


def contest_sid_valid(request, sid):
    """Checks if contest-local SID is still valid for current session."""
    _, resp = _runcgi(request, "new-master", SID=sid)
    title = _xpath(resp, "//title")
    return not title.text.endswith("Invalid session")


def contest_login(request, contest_id):
    """Generates a contest-local SID for a contest."""
    sid = srvctl_sid(request)
    hdrs, resp = _runcgi(request, "new-master", SID=sid, action=3, contest_id=contest_id)
    if "Location" not in hdrs:
        raise RuntimeError("something went wrong")
    return _breakdown_url(hdrs["Location"])["SID"]
