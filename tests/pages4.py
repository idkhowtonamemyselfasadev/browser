"""Microsoft-shaped sign-ins: an account picker that swaps the password
step in without ever reloading the document."""

# login.live.com: the e-mail box, a row of account tiles that put an
# address into that box without anybody typing, and a Next that
# replaces the whole step with the password screen — same document,
# no navigation, and the chosen address left standing as plain text
# where no <input> can be read from it.
TILES = """<!doctype html><meta charset=utf-8><title>Sign in</title>
<body style="font:16px sans-serif">
<h1>Sign in</h1>
<form id=f method=GET action="/done">
  <div id=stage1>
    <label for=loginfmt>Email, phone, or Skype</label>
    <input id=loginfmt name=loginfmt type=email autocomplete=username
           style="display:block;width:320px;height:32px">
    <button id=next type=button style="height:34px">Next</button>
  </div>
</form>
<div id=tiles style="margin-top:12px">
  <button type=button id=tileA style="height:34px">alt@example.com</button>
  <button type=button id=tileB style="height:34px">work@example.com</button>
</div>
<script>
var box = document.getElementById('loginfmt');
function pick(v) { return function () { box.value = v; }; }
document.getElementById('tileA').onclick = pick('alt@example.com');
document.getElementById('tileB').onclick = pick('work@example.com');
document.getElementById('next').onclick = function () {
  var who = box.value;
  document.getElementById('stage1').innerHTML =
    '<div id=who>' + who + '</div>' +
    '<input id=pw name=password type=password ' +
      'style="display:block;width:320px;height:32px">' +
    '<button id=signin type=submit style="height:34px">Sign in</button>';
};
</script>
</body>"""

# the same picker, except the address stays in a box the whole way
# through — the shape where the browser can always read it back
TILES_KEPT = """<!doctype html><meta charset=utf-8><title>Sign in</title>
<body style="font:16px sans-serif">
<h1>Sign in</h1>
<form id=f method=GET action="/done">
  <label for=loginfmt>Email, phone, or Skype</label>
  <input id=loginfmt name=loginfmt type=email autocomplete=username
         style="display:block;width:320px;height:32px">
  <div id=stage1>
    <button id=next type=button style="height:34px">Next</button>
  </div>
</form>
<div id=tiles style="margin-top:12px">
  <button type=button id=tileA style="height:34px">alt@example.com</button>
  <button type=button id=tileB style="height:34px">work@example.com</button>
</div>
<script>
var box = document.getElementById('loginfmt');
function pick(v) { return function () { box.value = v; }; }
document.getElementById('tileA').onclick = pick('alt@example.com');
document.getElementById('tileB').onclick = pick('work@example.com');
document.getElementById('next').onclick = function () {
  document.getElementById('stage1').innerHTML =
    '<input id=pw name=password type=password ' +
      'style="display:block;width:320px;height:32px">' +
    '<button id=signin type=submit style="height:34px">Sign in</button>';
};
</script>
</body>"""

# both boxes at once, with the site filling in an account of its own
PREFILLED = """<!doctype html><meta charset=utf-8><title>Log in</title>
<body style="font:16px sans-serif">
<form method=GET action="/done">
  <input id=user name=username type=text value="%s"
         style="display:block;width:320px;height:32px">
  <input id=pw name=password type=password
         style="display:block;width:320px;height:32px">
  <button id=signin type=submit style="height:34px">Log in</button>
</form>
</body>"""

# The same picker, but Next is a REAL navigation to a new document —
# which is where the identity stops being readable from the page and
# the browser has only its own note to go on. The tile writes the box
# programmatically, so the account that ends up in the note is not the
# one that was typed.
NAV_STEP1 = """<!doctype html><meta charset=utf-8><title>Sign in</title>
<body style="font:16px sans-serif">
<h1>Sign in</h1>
<form id=f>
  <label for=loginfmt>Email</label>
  <input id=loginfmt name=loginfmt type=email autocomplete=username
         style="display:block;width:320px;height:32px">
  <button id=next type=button style="height:34px">Next</button>
</form>
<button type=button id=tile style="height:34px">tile</button>
<script>
var box = document.getElementById('loginfmt');
document.getElementById('tile').onclick = function () {
  box.value = window.__T || 'decoy@example.com';   // nobody typed this
};
document.getElementById('next').onclick = function () {
  location.href = '/ms/nav-step2';
};
</script>
</body>"""

# step two of that: a password box, and an account the page merely
# claims to be signing in as — there is no box to read it out of
NAV_STEP2 = """<!doctype html><meta charset=utf-8><title>Password</title>
<body style="font:16px sans-serif">
<div id=who>stranger@example.com</div>
<form id=f method=GET action="/done">
  <input id=pw name=password type=password
         style="display:block;width:320px;height:32px">
  <button id=signin type=submit style="height:34px">Sign in</button>
</form>
</body>"""

# both boxes at once, and two buttons that rewrite the account without
# anybody typing — the shape where the browser has already filled a
# password before the account changes underneath it
SWAP = """<!doctype html><meta charset=utf-8><title>Log in</title>
<body style="font:16px sans-serif">
<form method=GET action="/done">
  <input id=user name=username type=text autocomplete=username
         style="display:block;width:320px;height:32px">
  <input id=pw name=password type=password
         style="display:block;width:320px;height:32px">
  <button id=signin type=submit style="height:34px">Log in</button>
</form>
<button type=button id=toA style="height:34px">A</button>
<button type=button id=toB style="height:34px">B</button>
<script>
var u = document.getElementById('user');
document.getElementById('toA').onclick = function () {
  u.value = 'A@example.com';
};
document.getElementById('toB').onclick = function () {
  u.value = 'B@example.com';
};
</script>
</body>"""

PAGES = {
    "/ms/tiles": TILES,
    "/ms/tiles-kept": TILES_KEPT,
    "/ms/prefilled-known": PREFILLED % "alt@example.com",
    "/ms/prefilled-stranger": PREFILLED % "work@example.com",
    "/ms/nav-step1": NAV_STEP1,
    "/ms/nav-step2": NAV_STEP2,
    "/ms/swap": SWAP,
}
