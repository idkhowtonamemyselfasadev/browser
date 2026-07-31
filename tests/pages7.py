"""Sign-in pages for the account chooser, served over a real HTTP
server. Two accounts are saved for the host in every case, so these are
the forms that must stay empty until he has picked one."""

# (a) the conventional both-at-once form. Submits by GET, so whatever
# actually left the browser is readable in the address afterwards.
BOTH = """<!doctype html><meta charset=utf-8><title>Log in</title>
<body style="font:16px sans-serif">
<h1>Log in</h1>
<form method=GET action="/done">
  <input id=user name=username type=email autocomplete=username
         style="display:block;width:320px;height:32px">
  <input id=pw name=password type=password
         style="display:block;width:320px;height:32px">
  <button id=signin type=submit style="height:34px">Log in</button>
</form>
</body>"""

# (b) two steps with a real navigation between them
STEP1 = """<!doctype html><meta charset=utf-8><title>Sign in</title>
<body style="font:16px sans-serif">
<h1>Sign in</h1>
<form method=GET action="/pick/step2">
  <label for=ap_email>E-mail</label>
  <input id=ap_email name=email type=email autocomplete=username
         style="display:block;width:320px;height:32px">
  <button id=next type=submit style="height:34px">Continue</button>
</form>
</body>"""

# step two has no username box at all: the account has to come from the
# half-login the chooser wrote, not from anything on screen
STEP2 = """<!doctype html><meta charset=utf-8><title>Password</title>
<body style="font:16px sans-serif">
<h1>Enter password</h1>
<form method=GET action="/done">
  <label for=ap_password>Password</label>
  <input id=ap_password name=password type=password
         style="display:block;width:320px;height:32px">
  <button id=signin type=submit style="height:34px">Sign in</button>
</form>
</body>"""

# (c) what Microsoft actually does: one document, the form swapped in
# place, no navigation, and no username box left on the second screen
SPA = """<!doctype html><meta charset=utf-8><title>Sign in</title>
<body style="font:16px sans-serif">
<h1>Sign in</h1>
<form id=f method=GET action="/done">
<div id=box>
  <input id=identifierId name=loginfmt type=email autocomplete=username
         style="display:block;width:320px;height:32px">
  <button id=next type=button style="height:34px">Next</button>
</div>
</form>
<script>
document.getElementById('next').addEventListener('click', function () {
  document.getElementById('box').innerHTML =
     '<input id=pw name=passwd type=password ' +
     'style="display:block;width:320px;height:32px">' +
     '<button id=signin type=submit style="height:34px">Sign in</button>';
});
</script>
</body>"""

DONE = """<!doctype html><meta charset=utf-8><title>done</title>
<body style="font:16px sans-serif">done</body>"""


def pages():
    return {
        "/pick/both": BOTH,
        "/pick/step1": STEP1,
        "/pick/step2": STEP2,
        "/pick/spa": SPA,
        "/done": DONE,
    }
