"""A sign-in that rebuilds its identifier box the way login.live.com
does — the shape in which the browser kept re-entering the saved
e-mail and no second account could be typed."""

# The identifier step, rendered by script into a container that gets
# thrown away and rebuilt. Two buttons stand in for the two ways a
# re-render lands: one carries the value across (React re-mounting a
# controlled input), one hands back a brand-new empty box.
RERENDER = """<!doctype html><meta charset=utf-8><title>Sign in</title>
<body style="font:16px sans-serif">
<h1>Sign in</h1>
<form id=f method=GET action="/done">
  <div id=host></div>
  <button id=next type=button style="height:34px">Next</button>
</form>
<button type=button id=rr style="height:34px">re-render</button>
<button type=button id=rrempty style="height:34px">re-render empty</button>
<script>
function build(keep) {
  var old = document.getElementById('loginfmt');
  var v = (keep && old) ? old.value : '';
  document.getElementById('host').innerHTML =
    '<label for=loginfmt>Email, phone, or Skype</label>' +
    '<input id=loginfmt name=loginfmt type=email autocomplete=username ' +
           'style="display:block;width:320px;height:32px">';
  document.getElementById('loginfmt').value = v;
}
build(false);
document.getElementById('rr').onclick = function () { build(true); };
document.getElementById('rrempty').onclick = function () { build(false); };
document.getElementById('next').onclick = function () {
  var who = document.getElementById('loginfmt').value;
  document.getElementById('host').innerHTML =
    '<div id=who>' + who + '</div>' +
    '<input id=pw name=password type=password ' +
           'style="display:block;width:320px;height:32px">';
  document.getElementById('next').outerHTML =
    '<button id=signin type=submit style="height:34px">Sign in</button>';
};
</script>
</body>"""

# The one-screen shape of the same thing: e-mail and password on the
# page at once. Here the browser's push at the PASSWORD stage carries a
# username too, so this is the second door the re-fill came through.
ONESCREEN = """<!doctype html><meta charset=utf-8><title>Log in</title>
<body style="font:16px sans-serif">
<form id=f method=GET action="/done">
  <input id=user name=username type=text autocomplete=username
         style="display:block;width:320px;height:32px">
  <input id=pw name=password type=password
         style="display:block;width:320px;height:32px">
  <button id=signin type=submit style="height:34px">Log in</button>
</form>
</body>"""

PAGES = {
    "/ms2/rerender": RERENDER,
    "/ms2/onescreen": ONESCREEN,
}
