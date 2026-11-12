"""Is he asked to save a password, on the ways real sites sign in?

Each page is typed into with real Qt keys and submitted with a real
click or Enter, then we look at whether the save offer came up.
Nothing here touches your data (see harness.boot)."""
import sys
import harness as H
from PyQt6.QtCore import Qt

B = H.boot()
app = H.app()

BOXES = ('<input id=u type=email autocomplete=username>'
         '<input id=p type=password autocomplete=current-password>')
PAGES = {
    "/step2": "<title>in</title>signed in",
    "/home": "<title>home</title>welcome",
    # 1. a plain form post
    "/classic": "<title>c</title><form method=post action=/x>" + BOXES
                + "<button id=go>Sign in</button></form>",
    # 2. fetch(), then a real navigation (very common)
    "/fetchnav": "<title>f</title><div>" + BOXES
                 + "<button id=go type=button>Sign in</button></div><script>"
                 "function go(){fetch('/api',{method:'POST',body:'x'})"
                 ".then(function(){location.href='/home'})}"
                 "document.getElementById('go').onclick=go;"
                 "document.getElementById('p').onkeydown=function(e){"
                 "if(e.key==='Enter')go()}</script>",
    # 3. single-page app: fetch(), pushState, the form is redrawn away
    "/spa": "<title>s</title><div id=app>" + BOXES
            + "<button id=go type=button>Log in</button></div><script>"
            "document.getElementById('go').onclick=function(){"
            "fetch('/api',{method:'POST',body:'x'}).then(function(){"
            "history.pushState({},'','/dashboard');"
            "document.getElementById('app').innerHTML='dashboard'})}</script>",
    # 4. form whose submit handler cancels and signs in with fetch()
    "/prevent": "<title>v</title><form id=f>" + BOXES
                + "<button id=go>Sign in</button></form><script>"
                "document.getElementById('f').onsubmit=function(e){"
                "e.preventDefault();fetch('/api',{method:'POST',body:'x'})"
                ".then(function(){location.href='/home'})}</script>",
    # 5. wrong password: the page shows an error and stays put
    "/stay": "<title>w</title><div>" + BOXES
             + "<button id=go type=button>Sign in</button><p id=e></p></div>"
             "<script>document.getElementById('go').onclick=function(){"
             "fetch('/api',{method:'POST',body:'x'}).then(function(){"
             "document.getElementById('e').textContent='wrong password'})}"
             "</script>",
    # 5b. wrong password, then he follows a real link away
    "/staylink": "<title>l</title><div>" + BOXES
             + "<button id=go type=button>Sign in</button>"
             "<a id=away href=/home>help</a></div>",
    # 6. signs in, then sends him to another host
    "/cross": "<title>x</title><div>" + BOXES
              + "<button id=go type=button>Sign in</button></div><script>"
              "document.getElementById('go').onclick=function(){"
              "location.href=location.href.replace('127.0.0.1','localhost')"
              ".replace('/cross','/home')}</script>",
}
srv = H.Server(PAGES)

br = B.Browser()
br.config["savePasswords"] = True
br.show()
H.spin(300)
view = br.current()

OFFERS = []
_orig = br._password_prompt


def _rec(host, username, update):
    OFFERS.append((host, username, (br._pw_pending or {}).get("password")))
    _orig(host, username, update)


br._password_prompt = _rec
RESULTS = []


def check(name, cond, extra=""):
    RESULTS.append((bool(cond), name))
    print(("  ok   " if cond else "  FAIL ") + name
          + (("  <%s>" % extra) if extra else ""))


def attempt(path, how, user, pw, want=True, label=""):
    del OFFERS[:]
    br._pw_pending = None
    br.vault.rows().clear()
    br.vault.data["entries"] = []
    H.load(view, srv.url(path))
    H.spin(600)
    H.click(view, "#u")
    H.type_text(view, user)
    H.click(view, "#p")
    H.type_text(view, pw)
    if how == "enter":
        H.key(view, Qt.Key.Key_Return)
    else:
        H.click(view, "#go")
    H.spin(2500)
    got = [o for o in OFFERS if o[2] == pw]
    if want:
        check("%s (%s): he is asked to save, once" % (path, how),
              len(OFFERS) == 1 and got and got[0][1] == user
              and got[0][0] == "127.0.0.1", OFFERS)
    else:
        check("%s (%s): %s" % (path, how, label), not OFFERS, OFFERS)


attempt("/classic", "click", "a@example.com", "pw-classic-1")
attempt("/fetchnav", "click", "b@example.com", "pw-fetchnav-1")
attempt("/fetchnav", "enter", "c@example.com", "pw-fetchnav-2")
attempt("/spa", "click", "d@example.com", "pw-spa-1")
attempt("/prevent", "click", "e@example.com", "pw-prevent-1")
attempt("/stay", "click", "f@example.com", "pw-wrong-1", want=False,
        label="a sign-in that went nowhere is not offered")
attempt("/cross", "click", "g@example.com", "pw-cross-1")

# wrong password, then a real link: never offered on the way out
del OFFERS[:]
br._pw_pending = None
H.load(view, srv.url("/staylink")); H.spin(600)
H.click(view, "#u"); H.type_text(view, "k@example.com")
H.click(view, "#p"); H.type_text(view, "pw-wrong-2")
H.click(view, "#go"); H.spin(800)
H.click(view, "#away"); H.spin(2000)
check("a wrong password then a link is not offered", not OFFERS, str(OFFERS))

# saved through the offer, it fills on the next visit
attempt("/fetchnav", "click", "h@example.com", "pw-fill-1")
br._pw_save_pending()
H.load(view, srv.url("/fetchnav"))
H.spin(2000)
H.click(view, "#p")      # the password waits for his own press
H.spin(800)
filled = H.js(view, "document.getElementById('p').value", B.PW_WORLD_ID)
user_box = H.js(view, "document.getElementById('u').value", B.PW_WORLD_ID)
check("the saved login fills on the next visit", filled == "pw-fill-1"
      and user_box == "h@example.com", str((user_box, filled)))

# a private tab never offers
del OFFERS[:]
br._pw_pending = None
pv = br.new_private_tab()
if pv is not None:
    H.load(pv, srv.url("/fetchnav"))
    H.spin(1500)
    H.click(pv, "#u"); H.type_text(pv, "p@example.com")
    H.click(pv, "#p"); H.type_text(pv, "pw-private-1")
    H.click(pv, "#go"); H.spin(2500)
    check("a private tab is never offered", not OFFERS, str(OFFERS))

bad = [n for ok, n in RESULTS if not ok]
print("%d checks, %d failed" % (len(RESULTS), len(bad)))
for n in bad:
    print("  FAILED:", n)
sys.stdout.flush()
H.os._exit(1 if bad else 0) if hasattr(H, "os") else sys.exit(1 if bad else 0)
