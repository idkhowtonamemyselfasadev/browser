"""Page shapes for the round-three defects (N1-N4)."""

# (N2) a newsletter box on a page whose layout also carries a hidden
# login modal somewhere else entirely
NL_WITH_MODAL = """<!doctype html><meta charset=utf-8><title>Shop</title>
<body style="font:16px sans-serif">
<div id=modal style="display:none">
  <form><input name=user type=text><input name=pass type=password></form>
</div>
<h1>Angebote</h1>
<form><p>Newsletter: nichts verpassen.</p>
  <input id=nl name=email type=email
         style="display:block;width:320px;height:32px">
  <button type=button style="height:34px">Abonnieren</button>
</form>
</body>"""

# (N2) an ordinary page whose URL merely contains "account"
ACCOUNT_NEWS = """<!doctype html><meta charset=utf-8><title>News</title>
<body style="font:16px sans-serif">
<h1>Neues aus dem Konto</h1>
<form><input id=nl name=email type=email
       style="display:block;width:320px;height:32px">
<button type=button style="height:34px">Abonnieren</button></form>
</body>"""

# (N2) an ordinary page that rewrites its own URL to look like a login
REWRITER = """<!doctype html><meta charset=utf-8><title>News</title>
<body style="font:16px sans-serif">
<form><input id=nl name=email type=email
       style="display:block;width:320px;height:32px">
<button type=button style="height:34px">Abonnieren</button></form>
<script>
setTimeout(function () {
  history.replaceState(null, '', '/signin?next=1');   // now a "login"
  document.body.appendChild(document.createElement('span'));  // poke it
}, 300);
</script>
</body>"""

# (N2) /author/someone must not read as an auth page
AUTHOR = """<!doctype html><meta charset=utf-8><title>Autor</title>
<body style="font:16px sans-serif">
<form><input id=nl name=email type=email
       style="display:block;width:320px;height:32px">
<button type=button style="height:34px">Abonnieren</button></form>
</body>"""

# (N2) a genuine sign-in with "Kontakt" planted in it: the filter must
# not be gameable in the suppressing direction
REAL_SIGNIN = """<!doctype html><meta charset=utf-8><title>x</title>
<body style="font:16px sans-serif">
<form>
  <p>Kontakt / contact / newsletter / abonnieren</p>
  <input id=ap_email name=email type=email autocomplete=username
         style="display:block;width:320px;height:32px">
  <input id=hidden_pw name=password type=password style="display:none">
  <button id=next type=button style="height:34px">Los</button>
</form>
</body>"""

# (N3) a two-step sign-in whose Next button only renders later
LATE = """<!doctype html><meta charset=utf-8><title>x</title>
<body style="font:16px sans-serif">
<div id=box>
  <input id=identifierId name=identifier type=email
         style="display:block;width:320px;height:32px">
</div>
<script>
setTimeout(function () {
  var b = document.createElement('button');
  b.id = 'next'; b.type = 'button'; b.textContent = 'Weiter';
  b.style.height = '34px';
  b.addEventListener('click', function () {
    document.getElementById('box').innerHTML =
      '<form id=f method=GET action="/done">' +
      '<input id=pw name=password type=password ' +
      'style="display:block;width:320px;height:32px">' +
      '<button id=signin type=submit style="height:34px">Anmelden</button>' +
      '</form>';
  });
  document.getElementById('box').appendChild(b);
}, 1200);
</script>
</body>"""

PAGES = {
    "/nl-with-modal": NL_WITH_MODAL,
    "/my-account/news": ACCOUNT_NEWS,
    "/plainpage": REWRITER,
    "/author/someone": AUTHOR,
    "/realsignin": REAL_SIGNIN,
    "/late": LATE,
}
