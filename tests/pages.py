"""The fake sign-ins, served over a real HTTP server."""

NEXT_FORM = """<!doctype html><meta charset=utf-8><title>Sign in</title>
<body style="font:16px sans-serif">
<h1>Sign in</h1>
<form method=GET action="/nav/step2">
  <label for=ap_email>E-mail or mobile phone number</label>
  <input id=ap_email name=email type=email autocomplete=username
         style="display:block;width:320px;height:32px">
  <button id=next type=submit style="height:34px">Continue</button>
</form>
</body>"""

NAV_STEP2 = """<!doctype html><meta charset=utf-8><title>Password</title>
<body style="font:16px sans-serif">
<h1>Sign in</h1>
<form method=GET action="/done">
  <label for=ap_password>Password</label>
  <input id=ap_password name=password type=password
         style="display:block;width:320px;height:32px">
  <button id=signin type=submit style="height:34px">Sign in</button>
</form>
</body>"""

# (b) one document, JavaScript swaps the field, no navigation at all
SPA = """<!doctype html><meta charset=utf-8><title>Sign in</title>
<body style="font:16px sans-serif">
<h1>Sign in</h1>
<div id=box>
  <input id=identifierId name=identifier type=email autocomplete=username
         style="display:block;width:320px;height:32px">
  <button id=next type=button style="height:34px">Next</button>
</div>
<script>
document.getElementById('next').addEventListener('click', function () {
  var box = document.getElementById('box');
  box.innerHTML = '<input id=pw name=Passwd type=password ' +
     'style="display:block;width:320px;height:32px">' +
     '<button id=signin type=button style="height:34px">Next</button>';
  document.getElementById('signin').addEventListener('click', function () {
    document.title = 'submitted';
  });
});
</script>
</body>"""

# (c) the conventional both-at-once form
BOTH = """<!doctype html><meta charset=utf-8><title>Log in</title>
<body style="font:16px sans-serif">
<form method=GET action="/done">
  <input id=user name=username type=text
         style="display:block;width:320px;height:32px">
  <input id=pw name=password type=password
         style="display:block;width:320px;height:32px">
  <button id=signin type=submit style="height:34px">Log in</button>
</form>
</body>"""

# (d) attack: the DOM swap puts the password step on another origin
HOP = """<!doctype html><meta charset=utf-8><title>Sign in</title>
<body style="font:16px sans-serif">
<form method=GET action="%s">
  <input id=ap_email name=email type=email autocomplete=username
         style="display:block;width:320px;height:32px">
  <button id=next type=submit style="height:34px">Continue</button>
</form>
</body>"""

# (e) attack: a planted password box nobody can see
HIDDEN = """<!doctype html><meta charset=utf-8><title>Sign in</title>
<body style="font:16px sans-serif">
<form>
  <input id=ap_email name=email type=email autocomplete=username
         style="display:block;width:320px;height:32px">
  <input id=trap name=trap type=password style="display:none">
  <input id=trap2 name=trap2 type=password
         style="position:absolute;width:1px;height:1px;opacity:0">
  <button id=next type=button style="height:34px">Continue</button>
</form>
</body>"""

# (f) attack: two visible password boxes (a sign-up / change form)
TWOPW = """<!doctype html><meta charset=utf-8><title>Register</title>
<body style="font:16px sans-serif">
<form>
  <input id=user name=username type=text
         style="display:block;width:320px;height:32px">
  <input id=pw1 name=password type=password
         style="display:block;width:320px;height:32px">
  <input id=pw2 name=confirm type=password
         style="display:block;width:320px;height:32px">
  <button id=go type=button style="height:34px">Create account</button>
</form>
</body>"""

# (g) a lone password box, no identifier anywhere (re-auth page)
LONEPW = """<!doctype html><meta charset=utf-8><title>Confirm</title>
<body style="font:16px sans-serif">
<form>
  <input id=pw name=password type=password
         style="display:block;width:320px;height:32px">
  <button id=go type=button style="height:34px">Confirm</button>
</form>
</body>"""

# a page with only a search box: the e-mail must not land in it
SEARCHY = """<!doctype html><meta charset=utf-8><title>Shop</title>
<body style="font:16px sans-serif">
<form><input id=q name=search type=text placeholder="Search"
       style="display:block;width:320px;height:32px">
<button type=button style="height:34px">Go</button></form>
</body>"""

# (D3) an identifier box that is NOT a login: a newsletter sign-up
NEWSLETTER = """<!doctype html><meta charset=utf-8><title>Shop</title>
<body style="font:16px sans-serif">
<h1>Angebote</h1>
<form><p>Newsletter: nichts verpassen.</p>
  <input id=nl name=email type=email
         style="display:block;width:320px;height:32px">
  <button type=button style="height:34px">Anmelden</button>
</form>
</body>"""

# (D3) a bare identifier box on an ordinary page
BARE = """<!doctype html><meta charset=utf-8><title>Contact</title>
<body style="font:16px sans-serif">
<input id=bare name=email type=text
       style="display:block;width:320px;height:32px">
</body>"""

# (D3) a sign-in that says so only in its URL (/account/login)
URLSIGNIN = """<!doctype html><meta charset=utf-8><title>Anmelden</title>
<body style="font:16px sans-serif">
<form method=GET action="/nav/step2">
  <input id=ap_email name=email type=email
         style="display:block;width:320px;height:32px">
  <button id=next type=submit style="height:34px">Los geht's</button>
</form>
</body>"""

DONE = "<!doctype html><meta charset=utf-8><title>done</title><body>done"


def pages(hop_target):
    return {
        "/nav/step1": NEXT_FORM,
        "/nav/step2": NAV_STEP2,
        "/spa": SPA,
        "/both": BOTH,
        "/hop/step1": HOP % hop_target,
        "/hop/step2": NAV_STEP2,
        "/hidden": HIDDEN,
        "/twopw": TWOPW,
        "/lonepw": LONEPW,
        "/searchy": SEARCHY,
        "/newsletter": NEWSLETTER,
        "/bare": BARE,
        "/account/login": URLSIGNIN,
        "/done": DONE,
    }
