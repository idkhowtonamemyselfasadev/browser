"""The master password's own page in the setup wizard.

It earns a page rather than a row because it is the only choice in this
wizard that cannot be taken back: forget the passphrase and the
passwords are gone. So the things that matter here are that the page
exists and is reachable, that the warning is the substance of it, that
a person who has switched the password manager off can still get past
it, and that a wizard finished with the switch off changes nothing.

Nothing here touches your data (see harness.boot).
"""
import json
import sys

import harness as H

B = H.boot()
app = H.app()

br = B.Browser()
br.show()
H.spin(400)
view = br.current()

RESULTS = []


def check(name, cond, extra=""):
    RESULTS.append((bool(cond), name))
    print(("  ok   " if cond else "  FAIL ") + name
          + (("  <%s>" % extra) if extra and not cond else ""))


def js(code):
    return H.js(view, code)


STR_VAULT = br._ui_str("wizVaultT")
STR_MASTER = br._ui_str("wizMasterT")
STR_NAV = br._ui_str("wizNavMaster")


def page_index(nav_name):
    """Where a page sits in wizPages(), by its rail name."""
    return js("(function(){var p=wizPages();for(var i=0;i<p.length;i++){"
              "if(p[i].nav===%s)return i;}return -1;})()"
              % json.dumps(nav_name))


def goto(nav_name):
    i = page_index(nav_name)
    if i is None or i < 0:
        return False
    js("gotoWiz(%d)" % i)
    H.spin(400)
    return True


def names():
    return js("(function(){return [].slice.call("
              "document.querySelectorAll('.wname')).map(function(e){"
              "return e.textContent;}).join('|');})()") or ""


def title():
    return js("(function(){var e=document.getElementById('wiztitle');"
              "return e?e.textContent:null;})()")


def stepno():
    return js("(function(){var e=document.getElementById('wizstepno');"
              "return e?e.textContent:null;})()")


H.load(view, B.START_PAGE.toString())
H.spin(700)

# ---------------------------------------------------------------- 1
print("\nthe wizard has nine steps, and the ninth is where it belongs")
js("openWiz(0)")
H.spin(400)
total = js("wizPages().length")
check("nine pages", total == 9, total)
i_priv = page_index(br._ui_str("wizNavPrivacy"))
i_master = page_index(STR_NAV)
i_links = page_index(br._ui_str("wizNavLinks"))
check("the master password page exists", i_master is not None and i_master >= 0,
      i_master)
check("it comes straight after Privacy", i_master == i_priv + 1,
      (i_priv, i_master))
check("and before Quick links", i_master < i_links, (i_master, i_links))
rail = js("(function(){return [].slice.call("
          "document.querySelectorAll('#wizsteps *')).map(function(e){"
          "return e.textContent;}).join('|');})()") or ""
check("the rail lists it", STR_NAV in rail, rail)

print("\nthe prose counts the steps the same way the array does")
for lang, word in (("en", "Nine"), ("de", "Neun")):
    text = B.UI_STRINGS[lang]["wizWelcomeP"]
    check("%s says %s quick steps" % (lang, word.lower()), word in text,
          text[:60])
    check("%s no longer says eight" % lang,
          "Eight" not in text and "Acht" not in text, text[:60])

# ---------------------------------------------------------------- 2
print("\nVault Password off: the page says so, and Next still works")
js("putVal('vaultPassword', false)")
check("on the master page", goto(STR_NAV))
check("its title is the master password", title() == STR_MASTER, title())
check("the step counter agrees",
      str(i_master + 1) in (stepno() or ""), stepno())
body = js("(function(){return document.getElementById('wizbody')"
          "? document.getElementById('wizbody').textContent : "
          "document.querySelector('.wizpage')"
          "? document.querySelector('.wizpage').textContent : "
          "document.body.textContent;})()") or ""
check("it says there is nothing to lock",
      br._ui_str("wizMasterNoVault") in body, body[:120])
check("no boxes are demanded", js("!document.getElementById('wizmasterA')"))
check("and no switch to answer either",
      STR_MASTER not in names(), names())
before = js("wizPage")
js("nextWiz()")
H.spin(400)
check("Next moves on", js("wizPage") == before + 1, (before, js("wizPage")))
check("nothing was set", br.vault_lock.enabled() is False)

# ---------------------------------------------------------------- 3
print("\nVault Password on: the offer, off, with the warning already there")
js("putVal('vaultPassword', true)")
check("back on the master page", goto(STR_NAV))
check("the switch is there", STR_MASTER in names(), names())
check("switched off", js(
    "(function(){var r=[].slice.call(document.querySelectorAll('.wrow'))"
    ".filter(function(e){var n=e.querySelector('.wname');"
    "return n && n.textContent===%s;})[0];"
    "return r?r.classList.contains('on'):null;})()"
    % json.dumps(STR_MASTER)) is False)
check("no boxes yet", js("!document.getElementById('wizmasterA')"))
check("but the warning is already on the page, before he touches anything",
      js("(function(){var e=document.querySelector('.wmwarnt');"
         "return e?e.textContent:null;})()") == br._ui_str("masterWarnT"))
check("with what it costs spelled out",
      js("(function(){var e=document.querySelector('.wmwarnb');"
         "return e?e.textContent:null;})()")
      == br._ui_str("wizMasterWarnB"))

# ---------------------------------------------------------------- 4
print("\nswitched on: the warning is the substance, and two boxes")
TOGGLE = ("(function(){var r=[].slice.call(document.querySelectorAll('.wrow'))"
          ".filter(function(e){var n=e.querySelector('.wname');"
          "return n && n.textContent===%s;})[0];if(r)r.onclick();})()"
          % json.dumps(STR_MASTER))
js(TOGGLE)
H.spin(350)
check("the warning headline is the Settings dialog's, word for word",
      js("(function(){var e=document.querySelector('.wmwarnt');"
         "return e?e.textContent:null;})()") == br._ui_str("masterWarnT"))
warn_b = js("(function(){var e=document.querySelector('.wmwarnb');"
            "return e?e.textContent:null;})()")
check("and the body is the wizard's own",
      warn_b == br._ui_str("wizMasterWarnB"), (warn_b or "")[:60])
check("which does not tell him to export, since he cannot here",
      "export" not in (warn_b or "").lower()
      and "exportier" not in (warn_b or "").lower(), (warn_b or "")[-60:])
check("two boxes", js("document.querySelectorAll('.wmpass').length") == 2)
check("neither shows what is typed",
      js("(function(){return [].slice.call("
         "document.querySelectorAll('.wmpass')).every(function(e){"
         "return e.type==='password';});})()") is True)
page_text = js("document.getElementById('wizmain').textContent") or ""
check("the fifteen-minute sentence is on this page, where he is deciding",
      br._ui_str("wizMasterAuto") in page_text, page_text[-200:])
check("and the minimum is stated",
      br._ui_str("masterMinHint") in page_text)
check("still nothing on disk", br.vault_lock.enabled() is False)

# ---------------------------------------------------------------- 5
print("\nit refuses a short one and a mistyped one")


def type_pair(a, b):
    js("(function(){var A=document.getElementById('wizmasterA'),"
       "Bx=document.getElementById('wizmasterB');"
       "A.value=%s;A.oninput();Bx.value=%s;Bx.oninput();})()"
       % (json.dumps(a), json.dumps(b)))
    H.spin(180)
    return js("(function(){var e=document.getElementById('wizmasternote');"
              "return e?e.textContent:null;})()")


note = type_pair("short", "short")
check("too short is refused", note == br._ui_str("masterShort"), note)
note = type_pair("a good long one", "a good long onf")
check("a mistyped second box is refused",
      note == br._ui_str("masterMismatch"), note)
check("still nothing on disk", br.vault_lock.enabled() is False)
note = type_pair("a good long one", "a good long one")
check("two matching long ones are accepted",
      note == br._ui_str("wizMasterSet"), note)

# ---------------------------------------------------------------- 6
print("\nEsc and back keeps what he typed")
js("document.getElementById('wizconfirm').classList.add('open')")
H.spin(150)
js("document.getElementById('wizcfStay').click()")
H.spin(200)
js("renderWiz()")
H.spin(300)
check("the boxes still hold it",
      js("(function(){var A=document.getElementById('wizmasterA');"
         "return A?A.value:null;})()") == "a good long one")
check("and the switch is still on",
      js("!!wizDraft.masterOn") is True)
check("nothing on disk until he leaves", br.vault_lock.enabled() is False)

# ---------------------------------------------------------------- 7
print("\nthe summary says it will be on")
js("gotoWiz(wizPages().length - 1)")
H.spin(600)
summary = js("(function(){var n=document.getElementById('wizsummary');"
             "if(!n)return null;return [].slice.call("
             "n.querySelectorAll('.sumrow')).map(function(r){"
             "return r.querySelector('.k').textContent + '=' + "
             "r.querySelector('.v').textContent;}).join('|');})()")
check("the master password is a row on the summary",
      br._ui_str("wizMasterSum") in (summary or ""), summary)
check("and it says On",
      (br._ui_str("wizMasterSum") + "=" + br._ui_str("wizMasterSumSet"))
      in (summary or ""), summary)

# ---------------------------------------------------------------- 8
print("\nfinishing applies it, once, with the final answer")
js("finishWiz()")
H.spin(1300)
check("the vault now has a master password", br.vault_lock.enabled() is True)
raw = (B.CONFIG_FILE.parent / "passwords.json").read_bytes()
check("the file on disk is sealed", raw[:4] == b"BPW2", raw[:4])
check("and the key file is gone",
      not (B.CONFIG_FILE.parent / "passwords.key").exists())
check("the passphrase he typed opens it",
      B.VaultLock(B.CONFIG_FILE.parent).unlock("a good long one") is True)
check("a different one does not",
      B.VaultLock(B.CONFIG_FILE.parent).unlock("a good long onf") is False)
check("this session can still use it, so a first login can be saved",
      br.vault_locked() is False)
check("with auto-lock armed", br.master_lock_minutes() == 15)
check("the passphrase is not left lying in the page",
      js("(wizDraft.masterA || wizDraft.masterB) ? 'still there' : 'gone'")
      == "gone")

# ---------------------------------------------------------------- 9
print("\nre-running setup does not offer a second one")
js("SET.masterOn = true")
check("the page believes one is set", js("!!SET.masterOn") is True)
js("openWiz(0)")
H.spin(300)
check("on the master page", goto(STR_NAV))
check("no boxes are offered", js("!document.getElementById('wizmasterA')"))
subs = js("(function(){return [].slice.call("
          "document.querySelectorAll('.wsub')).map(function(e){"
          "return e.textContent;}).join('|');})()") or ""
check("it points at Settings instead",
      br._ui_str("wizMasterHave") in subs, subs[:120])
js("leaveWiz()")
H.spin(400)

# --------------------------------------------------------------- 10
print("\na wizard finished with it OFF leaves everything as it was")
check("unlock to take it off", br.vault_lock.locked() is False)
check("removed", br.vault_lock.disable() is True)
br.vault = br.make_vault()
check("nothing is set again", br.vault_lock.enabled() is False)
js("SET.masterOn = false")
check("the page believes none is set", js("!!SET.masterOn") is False)
js("openWiz(0)")
H.spin(300)
check("on the master page", goto(STR_NAV))
check("the switch is there and off",
      STR_MASTER in names() and js("!!wizDraft.masterOn") is False, names())
js("finishWiz()")
H.spin(1200)
check("no master password was set", br.vault_lock.enabled() is False)
check("the vault is not locked", br.vault_locked() is False)
kept = B.CONFIG_FILE.parent / "passwords.json"
check("and nothing pretends otherwise on disk",
      (not kept.exists()) or kept.read_bytes()[:4] == b"BPW1",
      kept.read_bytes()[:4] if kept.exists() else "no file")
check("Vault Password itself is untouched", br.vault_password_on() is True)

print("\nswitched on and then off again before leaving sets nothing")
js("openWiz(0)")
H.spin(300)
check("on the master page", goto(STR_NAV))
js(TOGGLE)
H.spin(300)
js("(function(){var A=document.getElementById('wizmasterA'),"
   "Bx=document.getElementById('wizmasterB');"
   "A.value='a good long one';A.oninput();"
   "Bx.value='a good long one';Bx.oninput();})()")
H.spin(250)
check("it would have been set", js("masterOk()") is True)
js(TOGGLE)          # ...but he changes his mind
H.spin(300)
check("the boxes are gone again", js("!document.getElementById('wizmasterA')"))
js("finishWiz()")
H.spin(1200)
check("nothing was set", br.vault_lock.enabled() is False)

print()
bad = [n for ok, n in RESULTS if not ok]
print("%d checks, %d failed" % (len(RESULTS), len(bad)))
if bad:
    print("FAILED: " + ", ".join(bad))
else:
    print("all green")
sys.exit(1 if bad else 0)
