"""Sign-ins that walk from one subdomain to another.

Every other page in this suite lives on a single flat host, which is
why nothing here had ever crossed a two-step login with the vault's
host matching — and the vault matches families of hosts, not single
hosts. login.localhost, account.localhost and shop.localhost all
resolve to 127.0.0.1 on Linux, so a real navigation between siblings
of one parent can be driven for real.
"""

# Step one: the lone e-mail box. The form action is handed in, so the
# same page can point at its own host or at a sibling — and so can the
# value, because a page on the way past writing an account of its own
# choosing into the box is the thing the identity must survive.
STEP1 = """<!doctype html><meta charset=utf-8><title>Sign in</title>
<body style="font:16px sans-serif">
<h1>Sign in</h1>
<form method=GET action="%s">
  <label for=ap_email>E-mail</label>
  <input id=ap_email name=email type=email autocomplete=username value="%s"
         style="display:block;width:320px;height:32px">
  <button id=next type=submit style="height:34px">Continue</button>
</form>
</body>"""

# Step two: no username box at all — what Google, Amazon and Microsoft
# render, and the shape in which the browser has to know on its own
# whose password box this is.
STEP2 = """<!doctype html><meta charset=utf-8><title>Password</title>
<body style="font:16px sans-serif">
<h1>Sign in</h1>
<form method=GET action="/done">
  <label for=ap_password>Password</label>
  <input id=ap_password name=password type=password
         style="display:block;width:320px;height:32px">
  <button id=signin type=submit style="height:34px">Sign in</button>
</form>
</body>"""

DONE = "<!doctype html><meta charset=utf-8><title>done</title>done"


def pages(port):
    """Every path this suite serves, on whatever port the test got."""
    def to(host, path):
        return "http://%s.localhost:%d%s" % (host, port, path)
    def raw(host, path):
        return "http://%s:%d%s" % (host, port, path)
    return {
        # a hop between two siblings of one parent
        "/sub/step1": STEP1 % (to("account", "/sub/step2"), ""),
        "/sub/step2": STEP2,
        # the control: the same flow that never leaves its host
        "/same/step1": STEP1 % ("/same/step2", ""),
        "/same/step2": STEP2,
        # step one on the parent itself, step two on a subdomain
        "/down/step1": STEP1 % (to("shop", "/down/step2"), ""),
        "/down/step2": STEP2,
        # An open redirector. Step one is honest, on localhost. It is
        # routed through 127.0.0.1 — a wholly unrelated origin, with
        # nothing of his saved on it — which renders a sign-in of its
        # own with an account already written into the box, and sends
        # him back to the honest host for the password step.
        "/redir/a1": STEP1 % (raw("127.0.0.1", "/redir/hop"), ""),
        "/redir/hop": STEP1 % (raw("localhost", "/redir/a2"), "vip@corp.com"),
        "/redir/a2": STEP2,
        "/done": DONE,
    }
