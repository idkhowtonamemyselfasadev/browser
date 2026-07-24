#!/usr/bin/env python3
"""A minimal, island-styled web browser. Tabs, search bar, start page."""
import base64
import json
import os
import re
import sys
import uuid
import time
from pathlib import Path

CONFIG_FILE = Path.home() / ".local/share/browser/config.json"

# sites see prefers-color-scheme: dark and serve their native dark theme
# (0 = dark); must be set before Qt WebEngine starts
# (idempotent: a restarted child inherits the parent's flags)
if ("--blink-settings=preferredColorScheme=0"
        not in os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")):
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
        os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
        + " --blink-settings=preferredColorScheme=0")
# the embedded inspector (DevTools) only serves its frontend resources
# when remote debugging is enabled; bound to localhost by Chromium
os.environ.setdefault("QTWEBENGINE_REMOTE_DEBUGGING", "127.0.0.1:9222")

from PyQt6.QtCore import (
    QSize, Qt, QElapsedTimer, QEvent, QObject, QProcess, QStringListModel,
    QTimer, QUrl, QUrlQuery, pyqtSignal, pyqtSlot,
)
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtGui import (
    QColor, QDesktopServices, QIcon, QKeySequence, QPainter, QPixmap,
    QShortcut, QGuiApplication,
)
from PyQt6.QtWidgets import (
    QApplication, QCompleter, QFileDialog, QInputDialog, QLabel, QMainWindow,
    QMenu, QProgressBar, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QTabWidget, QTabBar, QToolButton, QWidgetAction,
)
from PyQt6.QtWebEngineCore import (
    QWebEnginePermission, QWebEngineProfile, QWebEnginePage, QWebEngineScript,
    QWebEngineSettings,
)
from PyQt6.QtNetwork import (
    QLocalServer, QLocalSocket, QNetworkAccessManager, QNetworkProxy,
    QNetworkRequest,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView

APP_DIR = Path(__file__).resolve().parent
# version query defeats the renderer's cache of local pages, so a new
# tab always shows the current start.html, not a stale cached copy
START_PAGE = QUrl.fromLocalFile(str(APP_DIR / "start.html"))
START_PAGE.setQuery("v=%d" % (APP_DIR / "start.html").stat().st_mtime)
SEARCH_URL = "https://www.google.com/search?q={}"
SEARCH_ENGINES = {
    "google": ("Google", "https://www.google.com/search?q={}"),
    "duckduckgo": ("DuckDuckGo", "https://duckduckgo.com/?q={}"),
    "bing": ("Bing", "https://www.bing.com/search?q={}"),
    "brave": ("Brave", "https://search.brave.com/search?q={}"),
    "ecosia": ("Ecosia", "https://www.ecosia.org/search?q={}"),
    "startpage": ("Startpage", "https://www.startpage.com/sp/search?query={}"),
}
SUGGEST_URL = "https://suggestqueries.google.com/complete/search"
DOWNLOAD_DIR = Path.home() / "Downloads"
HOSTS_FILE = Path.home() / ".local/share/browser/hosts.json"
HISTORY_FILE = Path.home() / ".local/share/browser/history.json"
HISTORY_PAGE = QUrl.fromLocalFile(str(APP_DIR / "history.html"))
HISTORY_PAGE.setQuery("v=%d" % (APP_DIR / "history.html").stat().st_mtime)
SETTINGS_PAGE = QUrl.fromLocalFile(str(APP_DIR / "settings.html"))
if (APP_DIR / "settings.html").exists():
    SETTINGS_PAGE.setQuery("v=%d" % (APP_DIR / "settings.html").stat().st_mtime)
HISTORY_MAX = 3000

# sites that ship their own dark theme (served via preferredColorScheme):
# force-dark would only slow them down repainting an already-dark page
NATIVE_DARK_SITES = {
    "github.com", "youtube.com", "reddit.com", "twitch.tv", "discord.com",
    "netflix.com", "spotify.com", "tiktok.com", "instagram.com",
    "modrinth.com", "duckduckgo.com",
}

# Google search stays LIGHT while the rest of the web is dark: the
# engine asks every site for dark, so Google's dark gray is inverted
# back to a light look (images and video are re-inverted to normal)
GOOGLE_BLACK_JS = r"""
(function () {
  if (!/^(www\.)?google\.[a-z.]+$/.test(location.hostname)) return;
  var s = document.createElement("style");
  s.textContent =
    "html, body { background: #000 !important; }" +
    ".sfbg, .minidiv, #searchform, #appbar, #sfcnt, #footcnt, #fbar," +
    " #footer, .appbar { background: #000 !important; }";
  (document.head || document.documentElement).appendChild(s);
})();
"""

GOOGLE_LIGHT_JS = r"""
(function () {
  if (!/^(www\.)?google\.[a-z.]+$/.test(location.hostname)) return;
  var bg = getComputedStyle(document.body).backgroundColor;
  var m = bg.match(/\d+/g);
  if (m && (+m[0] + +m[1] + +m[2]) / 3 > 128) return;  // already light
  var s = document.createElement("style");
  s.textContent =
    "html { filter: invert(1) hue-rotate(180deg); background: #fff !important; }" +
    "img, video, iframe, svg, canvas { filter: invert(1) hue-rotate(180deg); }";
  (document.head || document.documentElement).appendChild(s);
})();
"""

# what a site may ask for, in words the permission bar can show
PERMISSION_LABELS = {
    QWebEnginePermission.PermissionType.MediaAudioCapture:
        "use your microphone",
    QWebEnginePermission.PermissionType.MediaVideoCapture:
        "use your camera",
    QWebEnginePermission.PermissionType.MediaAudioVideoCapture:
        "use your microphone and camera",
    QWebEnginePermission.PermissionType.DesktopVideoCapture:
        "share your screen",
    QWebEnginePermission.PermissionType.DesktopAudioVideoCapture:
        "share your screen with audio",
    QWebEnginePermission.PermissionType.Notifications:
        "show notifications",
}

# sentinel: "new tab inherits the current tab's group"
INHERIT_GROUP = object()

# palette offered when creating a tab group
GROUP_COLORS = [
    ("Blue", "#89b4fa"), ("Pink", "#f38ba8"), ("Green", "#a6e3a1"),
    ("Yellow", "#f9e2af"), ("Purple", "#cba6f7"), ("Teal", "#94e2d5"),
    ("Orange", "#fab387"), ("Gray", "#6c7086"),
]

# UI translations for the browser's own pages (start, settings,
# history). Languages not listed fall back to English — websites and
# Google still follow the chosen language via Accept-Language.
UI_STRINGS = {
"en": {"settings":"Settings","search":"Search","searchEngine":"Search engine",
"appearance":"Appearance","whiteGoogle":"White Google",
"whiteGoogleHint":"Off = pitch-black Google",
"autoDarken":"Auto-darken light websites","pageZoom":"Page zoom",
"minFont":"Minimum text size","minFontHint":"Forces tiny website text to be at least this big.",
"browsing":"Browsing","reopenTabs":"Reopen tabs from last time",
"askDownload":"Ask where to save each download","translation":"Language",
"translateInto":"Browser and translate language",
"translateHint":"Changes this page, the start page, Google and the translate button.",
"privacy":"Privacy","saveHistory":"Save history","viewHistory":"View history",
"clearHistory":"Clear history","clearCookies":"Clear cookies",
"cookiesHint":"Clear cookies logs this virtual browser out everywhere.",
"updates":"Updates","checkUpdates":"Check for updates","setupT":"Setup",
"runSetup":"Run setup again","setupHint":"Drag the search bar, pick a wallpaper",
"filterPh":"Search\u2026","add":"Add","background":"Background",
"allSettings":"All settings","searchSite":"Search {}",
"wizWelcome":"Welcome! Let's set things up",
"wizDrag":"Grab the search bar and drag it wherever you want it.",
"center":"Center it again","nextBtn":"Next \u2192","wallpaper":"Wallpaper",
"pickWallpaper":"Pick a wallpaper for your start page.","finish":"Finish",
"history":"History","searchHistory":"Search history","clearAll":"Clear all",
"noHistory":"No history.","today":"Today","yesterday":"Yesterday",
"plugins":"Plugins",
"pluginsHint":"Userscripts (.user.js) in this folder run on matching pages.",
"reloadPlugins":"Reload plugins","noPlugins":"No plugins installed.","quickInstall":"Quick install","getMore":"Browse Greasy Fork","network":"Network (proxy)","proxyMode":"Proxy","proxySystem":"System","proxyDirect":"Direct (no proxy)","proxyCustom":"Custom","proxyType":"Type","proxyHost":"Host","proxyPort":"Port","proxyHint":"Pick a profile here or from the toolbar proxy button.","autoHint":"Auto routes each site by these rules; changes apply after a restart.","inspectorHint":"Press F12 on any page to open the inspector (DevTools).","fromFile":"From file\u2026","install":"Install","installed":"Installed \u2713"},
"de": {"settings":"Einstellungen","search":"Suche","searchEngine":"Suchmaschine",
"appearance":"Aussehen","whiteGoogle":"Wei\u00dfes Google",
"whiteGoogleHint":"Aus = pechschwarzes Google",
"autoDarken":"Helle Seiten abdunkeln","pageZoom":"Seitenzoom",
"minFont":"Minimale Textgr\u00f6\u00dfe","minFontHint":"Erzwingt, dass winziger Text mindestens so gro\u00df ist.",
"browsing":"Surfen","reopenTabs":"Tabs vom letzten Mal \u00f6ffnen",
"askDownload":"Bei Downloads nach Speicherort fragen","translation":"Sprache",
"translateInto":"Browser- und \u00dcbersetzungssprache",
"translateHint":"\u00c4ndert diese Seite, die Startseite, Google und den \u00dcbersetzen-Knopf.",
"privacy":"Privatsph\u00e4re","saveHistory":"Verlauf speichern",
"viewHistory":"Verlauf ansehen","clearHistory":"Verlauf l\u00f6schen",
"clearCookies":"Cookies l\u00f6schen",
"cookiesHint":"Cookies l\u00f6schen meldet diesen virtuellen Browser \u00fcberall ab.",
"updates":"Updates","checkUpdates":"Nach Updates suchen","setupT":"Einrichtung",
"runSetup":"Einrichtung neu starten","setupHint":"Suchleiste ziehen, Hintergrund w\u00e4hlen",
"filterPh":"Suchen\u2026","add":"Hinzuf\u00fcgen","background":"Hintergrund",
"allSettings":"Alle Einstellungen","searchSite":"{} durchsuchen",
"wizWelcome":"Willkommen! Richten wir alles ein",
"wizDrag":"Zieh die Suchleiste dorthin, wo du sie haben willst.",
"center":"Wieder zentrieren","nextBtn":"Weiter \u2192","wallpaper":"Hintergrundbild",
"pickWallpaper":"W\u00e4hle ein Hintergrundbild f\u00fcr deine Startseite.",
"finish":"Fertig","history":"Verlauf","searchHistory":"Verlauf durchsuchen",
"clearAll":"Alles l\u00f6schen","noHistory":"Kein Verlauf.","today":"Heute",
"yesterday":"Gestern",
"plugins":"Plugins",
"pluginsHint":"Userscripts (.user.js) in diesem Ordner laufen auf passenden Seiten.",
"reloadPlugins":"Plugins neu laden","noPlugins":"Keine Plugins installiert.","quickInstall":"Schnellinstallation","getMore":"Greasy Fork durchsuchen","network":"Netzwerk (Proxy)","proxyMode":"Proxy","proxySystem":"System","proxyDirect":"Direkt (kein Proxy)","proxyCustom":"Benutzerdefiniert","proxyType":"Typ","proxyHost":"Host","proxyPort":"Port","proxyHint":"W\u00e4hle ein Profil hier oder \u00fcber den Proxy-Knopf in der Leiste.","autoHint":"Auto leitet jede Seite nach diesen Regeln; \u00c4nderungen gelten nach einem Neustart.","inspectorHint":"F12 auf einer Seite \u00f6ffnet den Inspektor (DevTools).","fromFile":"Aus Datei\u2026","install":"Installieren","installed":"Installiert \u2713"},
"fr": {"settings":"Param\u00e8tres","search":"Recherche","searchEngine":"Moteur de recherche",
"appearance":"Apparence","whiteGoogle":"Google blanc",
"whiteGoogleHint":"D\u00e9sactiv\u00e9 = Google noir",
"autoDarken":"Assombrir les sites clairs","pageZoom":"Zoom de page",
"browsing":"Navigation","reopenTabs":"Rouvrir les onglets pr\u00e9c\u00e9dents",
"askDownload":"Demander o\u00f9 enregistrer chaque fichier","translation":"Langue",
"translateInto":"Langue du navigateur et de traduction",
"translateHint":"Change cette page, la page d'accueil, Google et le bouton de traduction.",
"privacy":"Confidentialit\u00e9","saveHistory":"Enregistrer l'historique",
"viewHistory":"Voir l'historique","clearHistory":"Effacer l'historique",
"clearCookies":"Effacer les cookies",
"cookiesHint":"Effacer les cookies d\u00e9connecte ce navigateur virtuel partout.",
"updates":"Mises \u00e0 jour","checkUpdates":"Rechercher des mises \u00e0 jour",
"setupT":"Configuration","runSetup":"Relancer la configuration",
"setupHint":"D\u00e9placez la barre, choisissez un fond",
"filterPh":"Rechercher\u2026","add":"Ajouter","background":"Fond d'\u00e9cran",
"allSettings":"Tous les param\u00e8tres","searchSite":"Rechercher sur {}",
"wizWelcome":"Bienvenue ! Configurons tout \u00e7a",
"wizDrag":"Saisissez la barre de recherche et placez-la o\u00f9 vous voulez.",
"center":"Recentrer","nextBtn":"Suivant \u2192","wallpaper":"Fond d'\u00e9cran",
"pickWallpaper":"Choisissez un fond pour votre page d'accueil.","finish":"Terminer",
"history":"Historique","searchHistory":"Rechercher dans l'historique",
"clearAll":"Tout effacer","noHistory":"Aucun historique.","today":"Aujourd'hui",
"yesterday":"Hier"},
"es": {"settings":"Ajustes","search":"B\u00fasqueda","searchEngine":"Buscador",
"appearance":"Apariencia","whiteGoogle":"Google blanco",
"whiteGoogleHint":"Apagado = Google negro","autoDarken":"Oscurecer sitios claros",
"pageZoom":"Zoom de p\u00e1gina","browsing":"Navegaci\u00f3n",
"reopenTabs":"Reabrir pesta\u00f1as anteriores",
"askDownload":"Preguntar d\u00f3nde guardar cada descarga","translation":"Idioma",
"translateInto":"Idioma del navegador y de traducci\u00f3n",
"translateHint":"Cambia esta p\u00e1gina, la p\u00e1gina de inicio, Google y el bot\u00f3n de traducir.",
"privacy":"Privacidad","saveHistory":"Guardar historial",
"viewHistory":"Ver historial","clearHistory":"Borrar historial",
"clearCookies":"Borrar cookies",
"cookiesHint":"Borrar cookies cierra la sesi\u00f3n de este navegador virtual en todas partes.",
"updates":"Actualizaciones","checkUpdates":"Buscar actualizaciones",
"setupT":"Configuraci\u00f3n","runSetup":"Repetir configuraci\u00f3n",
"setupHint":"Arrastra la barra, elige un fondo","filterPh":"Buscar\u2026",
"add":"A\u00f1adir","background":"Fondo","allSettings":"Todos los ajustes",
"searchSite":"Buscar en {}","wizWelcome":"\u00a1Bienvenido! Vamos a configurarlo",
"wizDrag":"Arrastra la barra de b\u00fasqueda a donde quieras.",
"center":"Centrar de nuevo","nextBtn":"Siguiente \u2192","wallpaper":"Fondo",
"pickWallpaper":"Elige un fondo para tu p\u00e1gina de inicio.","finish":"Listo",
"history":"Historial","searchHistory":"Buscar en el historial",
"clearAll":"Borrar todo","noHistory":"Sin historial.","today":"Hoy",
"yesterday":"Ayer"},
"it": {"settings":"Impostazioni","search":"Ricerca","searchEngine":"Motore di ricerca",
"appearance":"Aspetto","whiteGoogle":"Google bianco",
"whiteGoogleHint":"Spento = Google nero","autoDarken":"Scurisci i siti chiari",
"pageZoom":"Zoom pagina","browsing":"Navigazione",
"reopenTabs":"Riapri le schede precedenti",
"askDownload":"Chiedi dove salvare ogni download","translation":"Lingua",
"translateInto":"Lingua del browser e di traduzione",
"translateHint":"Cambia questa pagina, la pagina iniziale, Google e il pulsante traduci.",
"privacy":"Privacy","saveHistory":"Salva cronologia",
"viewHistory":"Vedi cronologia","clearHistory":"Cancella cronologia",
"clearCookies":"Cancella cookie",
"cookiesHint":"Cancellare i cookie disconnette questo browser virtuale ovunque.",
"updates":"Aggiornamenti","checkUpdates":"Cerca aggiornamenti",
"setupT":"Configurazione","runSetup":"Ripeti configurazione",
"setupHint":"Trascina la barra, scegli uno sfondo","filterPh":"Cerca\u2026",
"add":"Aggiungi","background":"Sfondo","allSettings":"Tutte le impostazioni",
"searchSite":"Cerca su {}","wizWelcome":"Benvenuto! Configuriamo tutto",
"wizDrag":"Trascina la barra di ricerca dove preferisci.",
"center":"Ricentra","nextBtn":"Avanti \u2192","wallpaper":"Sfondo",
"pickWallpaper":"Scegli uno sfondo per la pagina iniziale.","finish":"Fine",
"history":"Cronologia","searchHistory":"Cerca nella cronologia",
"clearAll":"Cancella tutto","noHistory":"Nessuna cronologia.","today":"Oggi",
"yesterday":"Ieri"},
"pt": {"settings":"Configura\u00e7\u00f5es","search":"Pesquisa","searchEngine":"Motor de busca",
"appearance":"Apar\u00eancia","whiteGoogle":"Google branco",
"whiteGoogleHint":"Desligado = Google preto","autoDarken":"Escurecer sites claros",
"pageZoom":"Zoom da p\u00e1gina","browsing":"Navega\u00e7\u00e3o",
"reopenTabs":"Reabrir abas da \u00faltima vez",
"askDownload":"Perguntar onde salvar cada download","translation":"Idioma",
"translateInto":"Idioma do navegador e de tradu\u00e7\u00e3o",
"translateHint":"Muda esta p\u00e1gina, a p\u00e1gina inicial, o Google e o bot\u00e3o de traduzir.",
"privacy":"Privacidade","saveHistory":"Salvar hist\u00f3rico",
"viewHistory":"Ver hist\u00f3rico","clearHistory":"Limpar hist\u00f3rico",
"clearCookies":"Limpar cookies",
"cookiesHint":"Limpar cookies desconecta este navegador virtual em todo lugar.",
"updates":"Atualiza\u00e7\u00f5es","checkUpdates":"Procurar atualiza\u00e7\u00f5es",
"setupT":"Configura\u00e7\u00e3o","runSetup":"Repetir configura\u00e7\u00e3o",
"setupHint":"Arraste a barra, escolha um fundo","filterPh":"Pesquisar\u2026",
"add":"Adicionar","background":"Plano de fundo","allSettings":"Todas as configura\u00e7\u00f5es",
"searchSite":"Pesquisar no {}","wizWelcome":"Bem-vindo! Vamos configurar",
"wizDrag":"Arraste a barra de pesquisa para onde quiser.",
"center":"Centralizar","nextBtn":"Avan\u00e7ar \u2192","wallpaper":"Plano de fundo",
"pickWallpaper":"Escolha um plano de fundo para sua p\u00e1gina inicial.","finish":"Concluir",
"history":"Hist\u00f3rico","searchHistory":"Pesquisar no hist\u00f3rico",
"clearAll":"Limpar tudo","noHistory":"Sem hist\u00f3rico.","today":"Hoje",
"yesterday":"Ontem"},
"nl": {"settings":"Instellingen","search":"Zoeken","searchEngine":"Zoekmachine",
"appearance":"Uiterlijk","whiteGoogle":"Wit Google",
"whiteGoogleHint":"Uit = pikzwart Google","autoDarken":"Lichte sites verdonkeren",
"pageZoom":"Paginazoom","browsing":"Browsen",
"reopenTabs":"Tabbladen van vorige keer heropenen",
"askDownload":"Vragen waar elke download wordt opgeslagen","translation":"Taal",
"translateInto":"Browser- en vertaaltaal",
"translateHint":"Verandert deze pagina, de startpagina, Google en de vertaalknop.",
"privacy":"Privacy","saveHistory":"Geschiedenis opslaan",
"viewHistory":"Geschiedenis bekijken","clearHistory":"Geschiedenis wissen",
"clearCookies":"Cookies wissen",
"cookiesHint":"Cookies wissen logt deze virtuele browser overal uit.",
"updates":"Updates","checkUpdates":"Zoeken naar updates","setupT":"Installatie",
"runSetup":"Installatie opnieuw","setupHint":"Sleep de zoekbalk, kies een achtergrond",
"filterPh":"Zoeken\u2026","add":"Toevoegen","background":"Achtergrond",
"allSettings":"Alle instellingen","searchSite":"Zoeken op {}",
"wizWelcome":"Welkom! Laten we alles instellen",
"wizDrag":"Sleep de zoekbalk naar waar je hem wilt hebben.",
"center":"Opnieuw centreren","nextBtn":"Volgende \u2192","wallpaper":"Achtergrond",
"pickWallpaper":"Kies een achtergrond voor je startpagina.","finish":"Klaar",
"history":"Geschiedenis","searchHistory":"Zoek in geschiedenis",
"clearAll":"Alles wissen","noHistory":"Geen geschiedenis.","today":"Vandaag",
"yesterday":"Gisteren"},
"pl": {"settings":"Ustawienia","search":"Szukanie","searchEngine":"Wyszukiwarka",
"appearance":"Wygl\u0105d","whiteGoogle":"Bia\u0142e Google",
"whiteGoogleHint":"Wy\u0142\u0105czone = czarne Google",
"autoDarken":"Przyciemniaj jasne strony","pageZoom":"Powi\u0119kszenie strony",
"browsing":"Przegl\u0105danie","reopenTabs":"Przywr\u00f3\u0107 karty z ostatniego razu",
"askDownload":"Pytaj, gdzie zapisa\u0107 ka\u017cdy plik","translation":"J\u0119zyk",
"translateInto":"J\u0119zyk przegl\u0105darki i t\u0142umaczenia",
"translateHint":"Zmienia t\u0119 stron\u0119, stron\u0119 startow\u0105, Google i przycisk t\u0142umaczenia.",
"privacy":"Prywatno\u015b\u0107","saveHistory":"Zapisuj histori\u0119",
"viewHistory":"Poka\u017c histori\u0119","clearHistory":"Wyczy\u015b\u0107 histori\u0119",
"clearCookies":"Wyczy\u015b\u0107 cookies",
"cookiesHint":"Wyczyszczenie cookies wylogowuje t\u0119 przegl\u0105dark\u0119 wsz\u0119dzie.",
"updates":"Aktualizacje","checkUpdates":"Sprawd\u017a aktualizacje",
"setupT":"Konfiguracja","runSetup":"Powt\u00f3rz konfiguracj\u0119",
"setupHint":"Przeci\u0105gnij pasek, wybierz tapet\u0119","filterPh":"Szukaj\u2026",
"add":"Dodaj","background":"T\u0142o","allSettings":"Wszystkie ustawienia",
"searchSite":"Szukaj w {}","wizWelcome":"Witaj! Skonfigurujmy wszystko",
"wizDrag":"Przeci\u0105gnij pasek wyszukiwania, gdzie chcesz.",
"center":"Wy\u015brodkuj","nextBtn":"Dalej \u2192","wallpaper":"Tapeta",
"pickWallpaper":"Wybierz tapet\u0119 strony startowej.","finish":"Gotowe",
"history":"Historia","searchHistory":"Szukaj w historii",
"clearAll":"Wyczy\u015b\u0107 wszystko","noHistory":"Brak historii.","today":"Dzisiaj",
"yesterday":"Wczoraj"},
"tr": {"settings":"Ayarlar","search":"Arama","searchEngine":"Arama motoru",
"appearance":"G\u00f6r\u00fcn\u00fcm","whiteGoogle":"Beyaz Google",
"whiteGoogleHint":"Kapal\u0131 = simsiyah Google",
"autoDarken":"A\u00e7\u0131k siteleri karart","pageZoom":"Sayfa yak\u0131nla\u015ft\u0131rma",
"browsing":"Gezinme","reopenTabs":"Son sekmeleri yeniden a\u00e7",
"askDownload":"Her indirmede nereye kaydedilece\u011fini sor","translation":"Dil",
"translateInto":"Taray\u0131c\u0131 ve \u00e7eviri dili",
"translateHint":"Bu sayfay\u0131, ba\u015flang\u0131\u00e7 sayfas\u0131n\u0131, Google'\u0131 ve \u00e7eviri d\u00fc\u011fmesini de\u011fi\u015ftirir.",
"privacy":"Gizlilik","saveHistory":"Ge\u00e7mi\u015fi kaydet",
"viewHistory":"Ge\u00e7mi\u015fi g\u00f6r","clearHistory":"Ge\u00e7mi\u015fi sil",
"clearCookies":"\u00c7erezleri sil",
"cookiesHint":"\u00c7erezleri silmek bu sanal taray\u0131c\u0131y\u0131 her yerden \u00e7\u0131k\u0131\u015f yapt\u0131r\u0131r.",
"updates":"G\u00fcncellemeler","checkUpdates":"G\u00fcncelleme ara","setupT":"Kurulum",
"runSetup":"Kurulumu tekrar \u00e7al\u0131\u015ft\u0131r",
"setupHint":"Arama \u00e7ubu\u011funu s\u00fcr\u00fckle, duvar ka\u011f\u0131d\u0131 se\u00e7",
"filterPh":"Ara\u2026","add":"Ekle","background":"Arka plan",
"allSettings":"T\u00fcm ayarlar","searchSite":"{} \u00fczerinde ara",
"wizWelcome":"Ho\u015f geldin! Her \u015feyi kural\u0131m",
"wizDrag":"Arama \u00e7ubu\u011funu istedi\u011fin yere s\u00fcr\u00fckle.",
"center":"Yeniden ortala","nextBtn":"\u0130leri \u2192","wallpaper":"Duvar ka\u011f\u0131d\u0131",
"pickWallpaper":"Ba\u015flang\u0131\u00e7 sayfan i\u00e7in duvar ka\u011f\u0131d\u0131 se\u00e7.",
"finish":"Bitti","history":"Ge\u00e7mi\u015f","searchHistory":"Ge\u00e7mi\u015fte ara",
"clearAll":"T\u00fcm\u00fcn\u00fc sil","noHistory":"Ge\u00e7mi\u015f yok.","today":"Bug\u00fcn",
"yesterday":"D\u00fcn"},
"ru": {"settings":"\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438","search":"\u041f\u043e\u0438\u0441\u043a",
"searchEngine":"\u041f\u043e\u0438\u0441\u043a\u043e\u0432\u0430\u044f \u0441\u0438\u0441\u0442\u0435\u043c\u0430",
"appearance":"\u0412\u043d\u0435\u0448\u043d\u0438\u0439 \u0432\u0438\u0434",
"whiteGoogle":"\u0411\u0435\u043b\u044b\u0439 Google",
"whiteGoogleHint":"\u0412\u044b\u043a\u043b = \u0447\u0451\u0440\u043d\u044b\u0439 Google",
"autoDarken":"\u0417\u0430\u0442\u0435\u043c\u043d\u044f\u0442\u044c \u0441\u0432\u0435\u0442\u043b\u044b\u0435 \u0441\u0430\u0439\u0442\u044b",
"pageZoom":"\u041c\u0430\u0441\u0448\u0442\u0430\u0431 \u0441\u0442\u0440\u0430\u043d\u0438\u0446\u044b",
"browsing":"\u041f\u0440\u043e\u0441\u043c\u043e\u0442\u0440",
"reopenTabs":"\u041e\u0442\u043a\u0440\u044b\u0432\u0430\u0442\u044c \u043f\u0440\u043e\u0448\u043b\u044b\u0435 \u0432\u043a\u043b\u0430\u0434\u043a\u0438",
"askDownload":"\u0421\u043f\u0440\u0430\u0448\u0438\u0432\u0430\u0442\u044c, \u043a\u0443\u0434\u0430 \u0441\u043e\u0445\u0440\u0430\u043d\u044f\u0442\u044c",
"translation":"\u042f\u0437\u044b\u043a",
"translateInto":"\u042f\u0437\u044b\u043a \u0431\u0440\u0430\u0443\u0437\u0435\u0440\u0430 \u0438 \u043f\u0435\u0440\u0435\u0432\u043e\u0434\u0430",
"translateHint":"\u041c\u0435\u043d\u044f\u0435\u0442 \u044d\u0442\u0443 \u0441\u0442\u0440\u0430\u043d\u0438\u0446\u0443, \u0441\u0442\u0430\u0440\u0442\u043e\u0432\u0443\u044e, Google \u0438 \u043a\u043d\u043e\u043f\u043a\u0443 \u043f\u0435\u0440\u0435\u0432\u043e\u0434\u0430.",
"privacy":"\u041a\u043e\u043d\u0444\u0438\u0434\u0435\u043d\u0446\u0438\u0430\u043b\u044c\u043d\u043e\u0441\u0442\u044c",
"saveHistory":"\u0421\u043e\u0445\u0440\u0430\u043d\u044f\u0442\u044c \u0438\u0441\u0442\u043e\u0440\u0438\u044e",
"viewHistory":"\u0418\u0441\u0442\u043e\u0440\u0438\u044f",
"clearHistory":"\u041e\u0447\u0438\u0441\u0442\u0438\u0442\u044c \u0438\u0441\u0442\u043e\u0440\u0438\u044e",
"clearCookies":"\u041e\u0447\u0438\u0441\u0442\u0438\u0442\u044c cookies",
"cookiesHint":"\u041e\u0447\u0438\u0441\u0442\u043a\u0430 cookies \u0432\u044b\u0445\u043e\u0434\u0438\u0442 \u0438\u0437 \u0432\u0441\u0435\u0445 \u0430\u043a\u043a\u0430\u0443\u043d\u0442\u043e\u0432.",
"updates":"\u041e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u044f",
"checkUpdates":"\u041f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u044f",
"setupT":"\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0430",
"runSetup":"\u041d\u0430\u0441\u0442\u0440\u043e\u0438\u0442\u044c \u0437\u0430\u043d\u043e\u0432\u043e",
"setupHint":"\u041f\u0435\u0440\u0435\u0442\u0430\u0449\u0438\u0442\u0435 \u0441\u0442\u0440\u043e\u043a\u0443, \u0432\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u043e\u0431\u043e\u0438",
"filterPh":"\u041f\u043e\u0438\u0441\u043a\u2026","add":"\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c",
"background":"\u0424\u043e\u043d","allSettings":"\u0412\u0441\u0435 \u043d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438",
"searchSite":"\u041f\u043e\u0438\u0441\u043a \u0432 {}",
"wizWelcome":"\u0414\u043e\u0431\u0440\u043e \u043f\u043e\u0436\u0430\u043b\u043e\u0432\u0430\u0442\u044c!",
"wizDrag":"\u041f\u0435\u0440\u0435\u0442\u0430\u0449\u0438\u0442\u0435 \u0441\u0442\u0440\u043e\u043a\u0443 \u043f\u043e\u0438\u0441\u043a\u0430 \u043a\u0443\u0434\u0430 \u0443\u0433\u043e\u0434\u043d\u043e.",
"center":"\u041f\u043e \u0446\u0435\u043d\u0442\u0440\u0443","nextBtn":"\u0414\u0430\u043b\u0435\u0435 \u2192",
"wallpaper":"\u041e\u0431\u043e\u0438",
"pickWallpaper":"\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u043e\u0431\u043e\u0438 \u0434\u043b\u044f \u0441\u0442\u0430\u0440\u0442\u043e\u0432\u043e\u0439.",
"finish":"\u0413\u043e\u0442\u043e\u0432\u043e","history":"\u0418\u0441\u0442\u043e\u0440\u0438\u044f",
"searchHistory":"\u041f\u043e\u0438\u0441\u043a \u0432 \u0438\u0441\u0442\u043e\u0440\u0438\u0438",
"clearAll":"\u041e\u0447\u0438\u0441\u0442\u0438\u0442\u044c \u0432\u0441\u0451",
"noHistory":"\u0418\u0441\u0442\u043e\u0440\u0438\u0438 \u043d\u0435\u0442.",
"today":"\u0421\u0435\u0433\u043e\u0434\u043d\u044f","yesterday":"\u0412\u0447\u0435\u0440\u0430"},
"ja": {"settings":"\u8a2d\u5b9a","search":"\u691c\u7d22","searchEngine":"\u691c\u7d22\u30a8\u30f3\u30b8\u30f3",
"appearance":"\u5916\u89b3","whiteGoogle":"\u767d\u3044Google",
"whiteGoogleHint":"\u30aa\u30d5 = \u771f\u3063\u9ed2\u306aGoogle",
"autoDarken":"\u660e\u308b\u3044\u30b5\u30a4\u30c8\u3092\u6697\u304f\u3059\u308b",
"pageZoom":"\u30da\u30fc\u30b8\u30ba\u30fc\u30e0","browsing":"\u30d6\u30e9\u30a6\u30b8\u30f3\u30b0",
"reopenTabs":"\u524d\u56de\u306e\u30bf\u30d6\u3092\u5fa9\u5143",
"askDownload":"\u4fdd\u5b58\u5148\u3092\u6bce\u56de\u78ba\u8a8d","translation":"\u8a00\u8a9e",
"translateInto":"\u30d6\u30e9\u30a6\u30b6\u3068\u7ffb\u8a33\u306e\u8a00\u8a9e",
"translateHint":"\u3053\u306e\u30da\u30fc\u30b8\u3001\u30b9\u30bf\u30fc\u30c8\u30da\u30fc\u30b8\u3001Google\u3001\u7ffb\u8a33\u30dc\u30bf\u30f3\u304c\u5909\u308f\u308a\u307e\u3059\u3002",
"privacy":"\u30d7\u30e9\u30a4\u30d0\u30b7\u30fc","saveHistory":"\u5c65\u6b74\u3092\u4fdd\u5b58",
"viewHistory":"\u5c65\u6b74\u3092\u898b\u308b","clearHistory":"\u5c65\u6b74\u3092\u6d88\u53bb",
"clearCookies":"Cookie\u3092\u6d88\u53bb",
"cookiesHint":"Cookie\u6d88\u53bb\u3067\u3053\u306e\u4eee\u60f3\u30d6\u30e9\u30a6\u30b6\u306f\u5168\u3066\u30ed\u30b0\u30a2\u30a6\u30c8\u3055\u308c\u307e\u3059\u3002",
"updates":"\u30a2\u30c3\u30d7\u30c7\u30fc\u30c8","checkUpdates":"\u66f4\u65b0\u3092\u78ba\u8a8d",
"setupT":"\u30bb\u30c3\u30c8\u30a2\u30c3\u30d7","runSetup":"\u30bb\u30c3\u30c8\u30a2\u30c3\u30d7\u3092\u3084\u308a\u76f4\u3059",
"setupHint":"\u691c\u7d22\u30d0\u30fc\u3092\u52d5\u304b\u3057\u3001\u58c1\u7d19\u3092\u9078\u3076",
"filterPh":"\u691c\u7d22\u2026","add":"\u8ffd\u52a0","background":"\u80cc\u666f",
"allSettings":"\u3059\u3079\u3066\u306e\u8a2d\u5b9a","searchSite":"{}\u3067\u691c\u7d22",
"wizWelcome":"\u3088\u3046\u3053\u305d\uff01\u8a2d\u5b9a\u3057\u307e\u3057\u3087\u3046",
"wizDrag":"\u691c\u7d22\u30d0\u30fc\u3092\u597d\u304d\u306a\u5834\u6240\u306b\u30c9\u30e9\u30c3\u30b0\u3002",
"center":"\u4e2d\u592e\u306b\u623b\u3059","nextBtn":"\u6b21\u3078 \u2192","wallpaper":"\u58c1\u7d19",
"pickWallpaper":"\u30b9\u30bf\u30fc\u30c8\u30da\u30fc\u30b8\u306e\u58c1\u7d19\u3092\u9078\u3093\u3067\u304f\u3060\u3055\u3044\u3002",
"finish":"\u5b8c\u4e86","history":"\u5c65\u6b74","searchHistory":"\u5c65\u6b74\u3092\u691c\u7d22",
"clearAll":"\u3059\u3079\u3066\u6d88\u53bb","noHistory":"\u5c65\u6b74\u306a\u3057\u3002",
"today":"\u4eca\u65e5","yesterday":"\u6628\u65e5"},
"zh": {"settings":"\u8bbe\u7f6e","search":"\u641c\u7d22","searchEngine":"\u641c\u7d22\u5f15\u64ce",
"appearance":"\u5916\u89c2","whiteGoogle":"\u767d\u8272Google",
"whiteGoogleHint":"\u5173\u95ed = \u7eaf\u9ed1Google",
"autoDarken":"\u8c03\u6697\u6d45\u8272\u7f51\u7ad9","pageZoom":"\u9875\u9762\u7f29\u653e",
"browsing":"\u6d4f\u89c8","reopenTabs":"\u6062\u590d\u4e0a\u6b21\u7684\u6807\u7b7e\u9875",
"askDownload":"\u6bcf\u6b21\u4e0b\u8f7d\u65f6\u8be2\u95ee\u4fdd\u5b58\u4f4d\u7f6e",
"translation":"\u8bed\u8a00","translateInto":"\u6d4f\u89c8\u5668\u548c\u7ffb\u8bd1\u8bed\u8a00",
"translateHint":"\u66f4\u6539\u6b64\u9875\u3001\u8d77\u59cb\u9875\u3001Google\u548c\u7ffb\u8bd1\u6309\u94ae\u3002",
"privacy":"\u9690\u79c1","saveHistory":"\u4fdd\u5b58\u5386\u53f2\u8bb0\u5f55",
"viewHistory":"\u67e5\u770b\u5386\u53f2","clearHistory":"\u6e05\u9664\u5386\u53f2",
"clearCookies":"\u6e05\u9664Cookie",
"cookiesHint":"\u6e05\u9664Cookie\u5c06\u9000\u51fa\u6b64\u865a\u62df\u6d4f\u89c8\u5668\u7684\u6240\u6709\u767b\u5f55\u3002",
"updates":"\u66f4\u65b0","checkUpdates":"\u68c0\u67e5\u66f4\u65b0","setupT":"\u8bbe\u7f6e\u5411\u5bfc",
"runSetup":"\u91cd\u65b0\u8fd0\u884c\u8bbe\u7f6e","setupHint":"\u62d6\u52a8\u641c\u7d22\u680f\uff0c\u9009\u62e9\u58c1\u7eb8",
"filterPh":"\u641c\u7d22\u2026","add":"\u6dfb\u52a0","background":"\u80cc\u666f",
"allSettings":"\u6240\u6709\u8bbe\u7f6e","searchSite":"\u5728{}\u641c\u7d22",
"wizWelcome":"\u6b22\u8fce\uff01\u6765\u8bbe\u7f6e\u4e00\u4e0b",
"wizDrag":"\u628a\u641c\u7d22\u680f\u62d6\u5230\u4f60\u60f3\u8981\u7684\u4f4d\u7f6e\u3002",
"center":"\u91cd\u65b0\u5c45\u4e2d","nextBtn":"\u4e0b\u4e00\u6b65 \u2192","wallpaper":"\u58c1\u7eb8",
"pickWallpaper":"\u4e3a\u8d77\u59cb\u9875\u9009\u62e9\u58c1\u7eb8\u3002","finish":"\u5b8c\u6210",
"history":"\u5386\u53f2","searchHistory":"\u641c\u7d22\u5386\u53f2",
"clearAll":"\u6e05\u9664\u5168\u90e8","noHistory":"\u6ca1\u6709\u5386\u53f2\u8bb0\u5f55\u3002",
"today":"\u4eca\u5929","yesterday":"\u6628\u5929"},
}

# built-in starter plugins (id -> (name, description, userscript source)).
# kept simple and self-contained — no Tampermonkey GM_* APIs, which the
# engine does not provide
STARTER_PLUGINS = {
    "yt-skip-ads": ("Skip YouTube ads",
        "Auto-clicks the skip button and speeds through unskippable ads.",
        """// ==UserScript==
// @name Skip YouTube ads
// @match *://*.youtube.com/*
// ==/UserScript==
setInterval(function () {
  var b = document.querySelector('.ytp-ad-skip-button, .ytp-ad-skip-button-modern, .ytp-skip-ad-button');
  if (b) b.click();
  var ad = document.querySelector('.ad-showing');
  var v = document.querySelector('video');
  if (ad && v && v.duration) { v.currentTime = v.duration; v.muted = true; }
}, 500);
"""),
    "yt-hide-shorts": ("Hide YouTube Shorts",
        "Removes Shorts shelves and the sidebar entry.",
        """// ==UserScript==
// @name Hide YouTube Shorts
// @match *://*.youtube.com/*
// ==/UserScript==
var css = document.createElement('style');
css.textContent =
  'ytd-reel-shelf-renderer, ytd-rich-shelf-renderer[is-shorts],' +
  'ytd-guide-entry-renderer:has(a[title="Shorts"]),' +
  'ytd-mini-guide-entry-renderer[aria-label="Shorts"] { display: none !important; }';
document.documentElement.appendChild(css);
"""),
    "cookie-away": ("Dismiss cookie banners",
        "Clicks away common cookie-consent popups automatically.",
        """// ==UserScript==
// @name Dismiss cookie banners
// @match *://*/*
// ==/UserScript==
setInterval(function () {
  var sels = ['#onetrust-accept-btn-handler','button[aria-label*="ccept"]',
    'button[title*="ccept"]','.fc-cta-consent','[data-testid="accept-button"]'];
  for (var i = 0; i < sels.length; i++) {
    var b = document.querySelector(sels[i]);
    if (b) { b.click(); break; }
  }
}, 1000);
"""),
    "text-select": ("Allow text selection",
        "Re-enables copying and selecting on sites that block it.",
        """// ==UserScript==
// @name Allow text selection
// @match *://*/*
// ==/UserScript==
var s = document.createElement('style');
s.textContent = '* { user-select: text !important; -webkit-user-select: text !important; }';
document.documentElement.appendChild(s);
document.addEventListener('copy', function (e) { e.stopPropagation(); }, true);
document.addEventListener('contextmenu', function (e) { e.stopPropagation(); }, true);
"""),
}

# english search aliases for the language menu
LANGUAGE_ALIASES = {
    "af": "afrikaans", "sq": "albanian", "am": "amharic", "ar": "arabic",
    "hy": "armenian", "az": "azerbaijani", "eu": "basque", "be": "belarusian",
    "bn": "bengali", "bs": "bosnian", "bg": "bulgarian", "ca": "catalan",
    "ceb": "cebuano", "zh-CN": "chinese simplified", "zh-TW": "chinese traditional",
    "co": "corsican", "hr": "croatian", "cs": "czech", "da": "danish",
    "nl": "dutch", "en": "english", "eo": "esperanto", "et": "estonian",
    "fi": "finnish", "fr": "french", "fy": "frisian", "gl": "galician",
    "ka": "georgian", "de": "german", "el": "greek", "gu": "gujarati",
    "ht": "haitian creole", "ha": "hausa", "haw": "hawaiian", "he": "hebrew",
    "hi": "hindi", "hmn": "hmong", "hu": "hungarian", "is": "icelandic",
    "ig": "igbo", "id": "indonesian", "ga": "irish", "it": "italian",
    "ja": "japanese", "jv": "javanese", "kn": "kannada", "kk": "kazakh",
    "km": "khmer", "rw": "kinyarwanda", "ko": "korean", "ku": "kurdish",
    "ky": "kyrgyz", "lo": "lao", "la": "latin", "lv": "latvian",
    "lt": "lithuanian", "lb": "luxembourgish", "mk": "macedonian",
    "mg": "malagasy", "ms": "malay", "ml": "malayalam", "mt": "maltese",
    "mi": "maori", "mr": "marathi", "mn": "mongolian", "my": "burmese",
    "ne": "nepali", "no": "norwegian", "ny": "chichewa", "or": "odia",
    "ps": "pashto", "fa": "persian farsi", "pl": "polish", "pt": "portuguese",
    "pa": "punjabi", "ro": "romanian", "ru": "russian", "sm": "samoan",
    "gd": "scots gaelic", "sr": "serbian", "st": "sesotho", "sn": "shona",
    "sd": "sindhi", "si": "sinhala", "sk": "slovak", "sl": "slovenian",
    "so": "somali", "es": "spanish", "su": "sundanese", "sw": "swahili",
    "sv": "swedish", "tl": "filipino tagalog", "tg": "tajik", "ta": "tamil",
    "tt": "tatar", "te": "telugu", "th": "thai", "tr": "turkish",
    "tk": "turkmen", "uk": "ukrainian", "ur": "urdu", "ug": "uyghur",
    "uz": "uzbek", "vi": "vietnamese", "cy": "welsh", "xh": "xhosa",
    "yi": "yiddish", "yo": "yoruba", "zu": "zulu",
}

# every language Google Translate speaks (code, native name)
LANGUAGES = [
    ("af", "Afrikaans"), ("sq", "Shqip"), ("am", "አማርኛ"), ("ar", "العربية"),
    ("hy", "Հայերեն"), ("az", "Azərbaycan"), ("eu", "Euskara"),
    ("be", "Беларуская"), ("bn", "বাংলা"), ("bs", "Bosanski"),
    ("bg", "Български"), ("ca", "Català"), ("ceb", "Cebuano"),
    ("zh-CN", "中文(简体)"), ("zh-TW", "中文(繁體)"), ("co", "Corsu"),
    ("hr", "Hrvatski"), ("cs", "Čeština"), ("da", "Dansk"),
    ("nl", "Nederlands"), ("en", "English"), ("eo", "Esperanto"),
    ("et", "Eesti"), ("fi", "Suomi"), ("fr", "Français"), ("fy", "Frysk"),
    ("gl", "Galego"), ("ka", "ქართული"), ("de", "Deutsch"),
    ("el", "Ελληνικά"), ("gu", "ગુજરાતી"), ("ht", "Kreyòl"),
    ("ha", "Hausa"), ("haw", "ʻŌlelo Hawaiʻi"), ("he", "עברית"),
    ("hi", "हिन्दी"), ("hmn", "Hmong"), ("hu", "Magyar"),
    ("is", "Íslenska"), ("ig", "Igbo"), ("id", "Indonesia"),
    ("ga", "Gaeilge"), ("it", "Italiano"), ("ja", "日本語"),
    ("jv", "Basa Jawa"), ("kn", "ಕನ್ನಡ"), ("kk", "Қазақ"),
    ("km", "ខ្មែរ"), ("rw", "Kinyarwanda"), ("ko", "한국어"),
    ("ku", "Kurdî"), ("ky", "Кыргызча"), ("lo", "ລາວ"),
    ("la", "Latina"), ("lv", "Latviešu"), ("lt", "Lietuvių"),
    ("lb", "Lëtzebuergesch"), ("mk", "Македонски"), ("mg", "Malagasy"),
    ("ms", "Melayu"), ("ml", "മലയാളം"), ("mt", "Malti"),
    ("mi", "Māori"), ("mr", "मराठी"), ("mn", "Монгол"),
    ("my", "မြန်မာ"), ("ne", "नेपाली"), ("no", "Norsk"),
    ("ny", "Chichewa"), ("or", "ଓଡ଼ିଆ"), ("ps", "پښتو"),
    ("fa", "فارسی"), ("pl", "Polski"), ("pt", "Português"),
    ("pa", "ਪੰਜਾਬੀ"), ("ro", "Română"), ("ru", "Русский"),
    ("sm", "Sāmoa"), ("gd", "Gàidhlig"), ("sr", "Српски"),
    ("st", "Sesotho"), ("sn", "Shona"), ("sd", "سنڌي"),
    ("si", "සිංහල"), ("sk", "Slovenčina"), ("sl", "Slovenščina"),
    ("so", "Soomaali"), ("es", "Español"), ("su", "Basa Sunda"),
    ("sw", "Kiswahili"), ("sv", "Svenska"), ("tl", "Filipino"),
    ("tg", "Тоҷикӣ"), ("ta", "தமிழ்"), ("tt", "Татар"),
    ("te", "తెలుగు"), ("th", "ไทย"), ("tr", "Türkçe"),
    ("tk", "Türkmen"), ("uk", "Українська"), ("ur", "اردو"),
    ("ug", "ئۇيغۇرچە"), ("uz", "Oʻzbek"), ("vi", "Tiếng Việt"),
    ("cy", "Cymraeg"), ("xh", "isiXhosa"), ("yi", "ייִדיש"),
    ("yo", "Yorùbá"), ("zu", "isiZulu"),
]

# domain guesses for the address bar ("wiki" -> wikipedia.org);
# visited sites are remembered and suggested too
COMMON_SITES = [
    "wikipedia.org", "youtube.com", "github.com", "google.com",
    "reddit.com", "amazon.de", "ebay.de", "netflix.com", "spotify.com",
    "twitch.tv", "instagram.com", "tiktok.com", "discord.com",
    "translate.google.com", "maps.google.com", "web.de", "gmx.net",
]

STYLE = """
* { font-family: "JetBrainsMono Nerd Font", "Inter", sans-serif; font-size: 13px; }
QMainWindow, #chrome { background: #000000; }

QLineEdit#urlbar {
    background: rgba(13, 13, 18, 230);
    color: #cdd6f4;
    border: 1px solid rgba(108, 112, 134, 70);
    border-radius: 0px;
    padding: 7px 16px;
    selection-background-color: #45475a;
    selection-color: #ffffff;
}
QLineEdit#urlbar:focus { border: 1px solid #a6adc8; }

QToolButton {
    background: rgba(13, 13, 18, 230);
    color: #cdd6f4;
    border: none;
    border-radius: 12px;
    padding: 5px 11px;
    font-weight: bold;
}
QToolButton:hover { background: #16161d; color: #ffffff; }

QTabWidget::pane { border: none; }
QTabBar { background: transparent; }
QTabBar::tab {
    background: rgba(13, 13, 18, 200);
    color: #a6adc8;
    border-radius: 0px;
    padding: 7px 6px 7px 14px;
    margin: 4px 3px 6px 3px;
}
QTabBar::tab:selected {
    background: #16161d;
    color: #cdd6f4;
    border: 1px solid rgba(108, 112, 134, 90);
}
QTabBar::tab:hover { color: #cdd6f4; }

#dlbar { background: #000000; border-top: 1px solid rgba(108, 112, 134, 50); }
#dlitem { background: rgba(13, 13, 18, 230); border-radius: 12px; }
QLabel#dlname { color: #cdd6f4; }
QLabel#dlinfo { color: #6c7086; font-size: 11px; }
QProgressBar {
    background: #16161d;
    border: none;
    border-radius: 3px;
    max-height: 6px;
}
QProgressBar::chunk { background: #89b4fa; border-radius: 3px; }

QToolButton#tabclose {
    background: rgba(108, 112, 134, 60);
    color: #cdd6f4;
    min-width: 18px; max-width: 18px;
    min-height: 18px; max-height: 18px;
    border-radius: 9px;
    padding: 0px;
    font-size: 12px;
    font-weight: normal;
}
QToolButton#tabclose:hover { background: rgba(243, 139, 168, 70); color: #f38ba8; }

#toast { background: #0d0d12; border: 1px solid rgba(108, 112, 134, 110); }
#permcard { background: #0d0d12; border: 1px solid rgba(108, 112, 134, 130); }
#permcard QLabel { color: #cdd6f4; }
#permcard QToolButton { padding: 6px 16px; border: 1px solid rgba(108, 112, 134, 90); }
#permcard QToolButton#permallow { background: #a6e3a1; color: #000000; border: none; }
#permcard QToolButton#permallow:hover { background: #c4f0c0; }
#toast QLabel { color: #cdd6f4; }

QMenu {
    background: #0d0d12;
    color: #cdd6f4;
    border: 1px solid rgba(108, 112, 134, 110);
    padding: 4px;
}
QMenu::item { padding: 6px 18px; }
QMenu::item:selected { background: #16161d; color: #ffffff; }
QMenu::separator { height: 1px; background: rgba(108, 112, 134, 70); margin: 4px 8px; }

QToolButton#groupbtn {
    font-size: 15px;
    padding: 5px 12px;
    margin: 4px 0 6px 6px;
    border-radius: 0px;
}
QToolButton#newtabbtn {
    padding: 0px;
    margin: 0px;
    border-radius: 0px;
    font-size: 15px;
}
"""


class GroupMenu(QMenu):
    """The book-button menu; right-clicking a group offers to delete it."""

    def __init__(self, browser):
        super().__init__(browser)
        self.browser = browser

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            action = self.actionAt(event.position().toPoint())
            group = action.data() if action else None
            if group:
                sub = QMenu(self)
                delete = sub.addAction("Delete \u201c%s\u201d" % group)
                chosen = sub.exec(event.globalPosition().toPoint())
                if chosen is delete:
                    self.browser.delete_group(group)
                self.close()
                return
        super().mouseReleaseEvent(event)


class GroupTabBar(QTabBar):
    """Chrome-style painting: group headers as colored pills, group
    members with a colored underline."""

    def __init__(self, browser):
        super().__init__()
        self.browser = browser

    def _tabs(self):
        return getattr(self.browser, "tabs", None)

    def tabSizeHint(self, index):
        size = super().tabSizeHint(index)
        tabs = self._tabs()
        w = tabs.widget(index) if tabs else None
        if w is not None and getattr(w, "group_header", None) is not None:
            width = self.fontMetrics().horizontalAdvance(w.group_header) + 30
            return QSize(max(width, 44), size.height())
        if tabs is None:
            return QSize(min(max(size.width(), 160), 240), size.height())
        # tabs share the bar width and shrink as more open, like Chrome
        members = 0
        pills = 0
        for i in range(self.count()):
            if not self.isTabVisible(i):
                continue
            wi = tabs.widget(i)
            if wi is None:
                continue
            if getattr(wi, "group_header", None) is not None:
                pills += (self.fontMetrics().horizontalAdvance(wi.group_header)
                          + 30 + 6)
            else:
                members += 1
        available = self.width() - pills - 46  # room for the + button
        share = available // max(1, members) - 6  # per-tab margins
        return QSize(max(34, min(240, share)), size.height())

    def tabLayoutChange(self):
        super().tabLayoutChange()
        if getattr(self.browser, "tabs", None):
            update = getattr(self.browser, "_update_close_buttons", None)
            if update is not None:
                update()
            place = getattr(self.browser, "_place_newtab", None)
            if place is not None:
                place()

    def paintEvent(self, event):
        super().paintEvent(event)
        tabs = self._tabs()
        if tabs is None:
            return
        painter = QPainter(self)
        for i in range(self.count()):
            if not self.isTabVisible(i):
                continue
            w = tabs.widget(i)
            if w is None:
                continue
            rect = self.tabRect(i)
            header = getattr(w, "group_header", None)
            if header is not None:
                color = QColor(self.browser.group_colors.get(header, "#6c7086"))
                pill = rect.adjusted(3, 8, -3, -10)
                painter.fillRect(pill, color)
                painter.setPen(QColor("#000000"))
                painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, header)
            else:
                group = getattr(w, "group", None)
                if group is not None:
                    color = QColor(self.browser.group_colors.get(group, "#6c7086"))
                    painter.fillRect(rect.x() + 2, rect.bottom() - 2,
                                     rect.width() - 4, 3, color)
        painter.end()


class TabWidget(QTabWidget):
    def __init__(self, browser):
        super().__init__()
        self.setTabBar(GroupTabBar(browser))


class Bridge(QObject):
    """Exposed to the start/history pages via QWebChannel."""

    updateFinished = pyqtSignal(str)

    def __init__(self, browser):
        super().__init__()
        self.browser = browser
        self._updating = None

    @pyqtSlot()
    def runUpdate(self):
        """Pull the newest version from GitHub (async; result via signal)."""
        if self._updating is not None:
            return
        proc = QProcess(self)
        self._updating = proc
        proc.setWorkingDirectory(str(APP_DIR))
        proc.finished.connect(lambda *_: self._update_done(proc))
        proc.errorOccurred.connect(lambda *_: self._update_done(proc))
        proc.start("git", ["pull", "--ff-only"])

    def _update_done(self, proc):
        if self._updating is not proc:
            return
        self._updating = None
        out = bytes(proc.readAllStandardOutput()).decode(errors="replace")
        err = bytes(proc.readAllStandardError()).decode(errors="replace")
        proc.deleteLater()
        if proc.exitStatus() != QProcess.ExitStatus.NormalExit or proc.error() == QProcess.ProcessError.FailedToStart:
            msg = "Update needs git and a cloned copy of the repo."
        elif proc.exitCode() != 0:
            msg = "Update failed: " + (err.strip().splitlines() or ["unknown error"])[-1]
        elif "Already up to date" in out:
            msg = "You have the newest version \u2713"
        else:
            msg = "Updated! Restart the browser to finish."
        self.updateFinished.emit(msg)

    @pyqtSlot(result=bool)
    def historyEnabled(self):
        return self.browser.config.get("history", True)

    @pyqtSlot(bool)
    def setHistoryEnabled(self, enabled):
        self.browser.config["history"] = enabled
        self.browser.save_config()

    @pyqtSlot(result=str)
    def uiStrings(self):
        lang = self.browser.config.get("translateLang", "de")
        strings = dict(UI_STRINGS["en"])
        override = UI_STRINGS.get(lang) or UI_STRINGS.get(lang.split("-")[0])
        if override:
            strings.update(override)
        strings["lang"] = lang
        return json.dumps(strings)

    @pyqtSlot(result=str)
    def getSettings(self):
        c = self.browser.config
        key = c.get("searchEngine", "google")
        if key not in SEARCH_ENGINES:
            key = "google"
        name, template = SEARCH_ENGINES[key]
        action, _, param = template.partition("?")
        return json.dumps({
            "searchEngine": key,
            "engines": [[k, v[0]] for k, v in SEARCH_ENGINES.items()],
            "searchName": name,
            "searchAction": action,
            "searchParam": param.split("=")[0] if param else "q",
            "googleLight": c.get("googleLight", True),
            "forceDark": c.get("forceDark", True),
            "restoreTabs": c.get("restoreTabs", True),
            "zoom": c.get("zoom", 1.0),
            "minFont": c.get("minFont", 0),
            "askDownload": bool(c.get("askDownload", False)),
            "history": c.get("history", True),
            "translateLang": c.get("translateLang", "de"),
            "languages": [[code, name, LANGUAGE_ALIASES.get(code, "")]
                          for code, name in LANGUAGES],
            "activeProxy": c.get("activeProxy", "system"),
            "proxyProfiles": c.get("proxyProfiles", []),
            "proxyAuto": c.get("proxyAuto") or {"rules": [], "default": "direct"},
        })

    @pyqtSlot(str)
    def setProxyAuto(self, auto_json):
        try:
            auto = json.loads(auto_json)
        except ValueError:
            return
        self.browser.config["proxyAuto"] = auto
        self.browser.save_config()
        self.browser.apply_proxy()

    @pyqtSlot(str)
    def setActiveProxy(self, name):
        self.browser.set_active_proxy(name)

    @pyqtSlot(str)
    def saveProxyProfile(self, profile_json):
        try:
            prof = json.loads(profile_json)
        except ValueError:
            return
        name = (prof.get("name") or "").strip()
        if not name or name in ("system", "direct"):
            return
        prof["name"] = name
        profs = [p for p in self.browser.config.get("proxyProfiles", [])
                 if p.get("name") != name]
        profs.append(prof)
        self.browser.config["proxyProfiles"] = profs
        self.browser.save_config()
        self.browser.apply_proxy()

    @pyqtSlot(str)
    def deleteProxyProfile(self, name):
        b = self.browser
        b.config["proxyProfiles"] = [
            p for p in b.config.get("proxyProfiles", [])
            if p.get("name") != name]
        if b.config.get("activeProxy") == name:
            b.config["activeProxy"] = "system"
        b.save_config()
        b.apply_proxy()

    @pyqtSlot(str, str)
    def setSetting(self, key, value_json):
        try:
            value = json.loads(value_json)
        except ValueError:
            return
        browser = self.browser
        browser.config[key] = value
        browser.save_config()
        if key == "googleLight":
            browser.refresh_google_scripts()
        elif key == "translateLang":
            browser.apply_language()
        elif key == "proxy":
            browser.apply_proxy()
        elif key == "forceDark":
            for profile in ([browser.profile]
                            + list(browser.session_profiles.values())):
                profile.settings().setAttribute(
                    QWebEngineSettings.WebAttribute.ForceDarkMode, bool(value))
        elif key == "zoom":
            for i in range(browser.tabs.count()):
                w = browser.tabs.widget(i)
                if hasattr(w, "setZoomFactor"):
                    w.setZoomFactor(float(value))
        elif key == "minFont":
            browser.apply_font_size()
            for i in range(browser.tabs.count()):
                w = browser.tabs.widget(i)
                if hasattr(w, "reload") and w.url().scheme() in ("http", "https"):
                    w.reload()

    @pyqtSlot()
    def clearCookies(self):
        """Wipe cookies + cache of the CURRENT virtual browser only."""
        view = self.browser.current()
        profile = (view.page().profile() if view is not None
                   else self.browser.profile)
        profile.cookieStore().deleteAllCookies()
        profile.clearHttpCache()

    @pyqtSlot()
    def requestSetup(self):
        self.browser._setup_flag = True

    @pyqtSlot(result=bool)
    def popSetupFlag(self):
        flag = getattr(self.browser, "_setup_flag", False)
        self.browser._setup_flag = False
        return flag

    @pyqtSlot(result=bool)
    def googleLight(self):
        return self.browser.config.get("googleLight", True)

    @pyqtSlot(bool)
    def setGoogleLight(self, on):
        self.browser.config["googleLight"] = bool(on)
        self.browser.save_config()
        self.browser.refresh_google_scripts()

    @pyqtSlot(result=str)
    def getStartData(self):
        """Start-page setup shared across all cookie jars."""
        return json.dumps(self.browser.config.get("startPage", {}))

    @pyqtSlot(str)
    def setStartData(self, data):
        try:
            self.browser.config["startPage"] = json.loads(data)
        except ValueError:
            return
        self.browser.save_config()

    @pyqtSlot(result=str)
    def getHistory(self):
        return json.dumps(self.browser.history)

    @pyqtSlot()
    def clearHistory(self):
        self.browser.history = []
        self.browser.save_history()

    @pyqtSlot(result=str)
    def getPlugins(self):
        b = self.browser
        return json.dumps({
            "plugins": [n[len("plugin-"):] for n in b.plugin_script_names],
            "folder": str(b.plugins_dir),
        })

    @pyqtSlot(result=str)
    def reloadPlugins(self):
        self.browser.reload_plugins()
        return self.getPlugins()

    @pyqtSlot(result=str)
    def starterPlugins(self):
        return json.dumps([{"id": k, "name": v[0], "desc": v[1]}
                           for k, v in STARTER_PLUGINS.items()])

    @pyqtSlot(str, result=bool)
    def installStarter(self, plugin_id):
        return self.browser.install_starter(plugin_id)

    @pyqtSlot()
    def addPluginFromFile(self):
        self.browser.add_plugin_from_file()

    @pyqtSlot(str, str)
    def savePlugin(self, filename, source):
        self.browser.save_plugin(filename, source)


class WebView(QWebEngineView):
    def __init__(self, browser, profile):
        super().__init__()
        self.browser = browser
        self.attach_profile(profile)

    def attach_profile(self, profile):
        old = self.page()
        page = QWebEnginePage(profile, self)
        channel = QWebChannel(page)
        channel.registerObject("bridge", self.browser.bridge)
        page.setWebChannel(channel)
        page.fullScreenRequested.connect(self._fullscreen)
        page.permissionRequested.connect(self.browser._permission_requested)
        page.proxyAuthenticationRequired.connect(self.browser._proxy_auth)
        self.setPage(page)
        if old is not None and old is not page:
            try:
                old.deleteLater()
            except RuntimeError:
                pass  # Qt already disposed of the replaced page

    def createWindow(self, wtype):
        # tab for a link opened by a page (ctrl+click, middle-click,
        # target=_blank); the engine loads the URL itself, so don't load
        # the start page. Ctrl/middle-click = background tab, like Chrome.
        background = (wtype ==
                      QWebEnginePage.WebWindowType.WebBrowserBackgroundTab)
        return self.browser.new_tab(switch=not background, blank=True)

    def _fullscreen(self, request):
        request.accept()
        self.browser.set_fullscreen(request.toggleOn())


def fmt_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def fmt_time(seconds):
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} s"
    if seconds < 3600:
        return f"{seconds // 60} min {seconds % 60} s"
    return f"{seconds // 3600} h {seconds % 3600 // 60} min"


class DownloadWidget(QWidget):
    """One entry in the download bar: name, progress, speed, time left."""

    def __init__(self, request, on_dismiss):
        super().__init__(objectName="dlitem")
        self.req = request
        self.on_dismiss = on_dismiss
        self.clock = QElapsedTimer()
        self.clock.start()
        self.last_bytes = 0
        self.last_ms = 0
        self.speed = 0.0

        self.setFixedWidth(360)
        name = request.downloadFileName()
        self.name = QLabel(objectName="dlname")
        self.name.setText(self.fontMetrics().elidedText(
            name, Qt.TextElideMode.ElideMiddle, 230))
        self.name.setToolTip(name)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.info = QLabel("Starting…", objectName="dlinfo")

        self.open_btn = QToolButton(text="Open")
        self.open_btn.hide()
        self.open_btn.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(self.req.downloadDirectory())))
        self.close_btn = QToolButton(text="✕")
        self.close_btn.clicked.connect(self._cancel_or_dismiss)

        grid = QGridLayout(self)
        grid.setContentsMargins(12, 8, 8, 8)
        grid.setVerticalSpacing(4)
        grid.addWidget(self.name, 0, 0)
        grid.addWidget(self.open_btn, 0, 1)
        grid.addWidget(self.close_btn, 0, 2)
        grid.addWidget(self.bar, 1, 0, 1, 3)
        grid.addWidget(self.info, 2, 0, 1, 3)

        request.receivedBytesChanged.connect(self._progress)
        request.totalBytesChanged.connect(self._progress)
        request.stateChanged.connect(self._state_changed)

    def _progress(self):
        if self.req.state() != self.req.DownloadState.DownloadInProgress:
            return
        received, total = self.req.receivedBytes(), self.req.totalBytes()
        ms = self.clock.elapsed()
        if ms - self.last_ms >= 300:
            instant = (received - self.last_bytes) / ((ms - self.last_ms) / 1000)
            self.speed = instant if not self.speed else 0.7 * self.speed + 0.3 * instant
            self.last_bytes, self.last_ms = received, ms
        parts = []
        if total > 0:
            self.bar.setRange(0, 1000)
            self.bar.setValue(round(received / total * 1000))
            parts.append(f"{fmt_size(received)} / {fmt_size(total)}")
        else:
            self.bar.setRange(0, 0)  # size unknown: busy animation
            parts.append(fmt_size(received))
        if self.speed > 0:
            parts.append(f"{fmt_size(self.speed)}/s")
            if total > 0:
                parts.append(f"{fmt_time((total - received) / self.speed)} left")
        self.info.setText(" · ".join(parts))

    def _state_changed(self, state):
        St = self.req.DownloadState
        if state == St.DownloadCompleted:
            self.bar.setRange(0, 1000)
            self.bar.setValue(1000)
            self.info.setText(f"Done · {fmt_size(self.req.receivedBytes())}")
            self.open_btn.show()
        elif state == St.DownloadCancelled:
            self.bar.setRange(0, 1000)
            self.info.setText("Cancelled")
        elif state == St.DownloadInterrupted:
            self.bar.setRange(0, 1000)
            self.info.setText("Failed: " + self.req.interruptReasonString())

    def _cancel_or_dismiss(self):
        if self.req.state() == self.req.DownloadState.DownloadInProgress:
            self.req.cancel()
        else:
            self.on_dismiss(self)


class Browser(QMainWindow):
    def __init__(self, initial_url=None):
        super().__init__()
        self._initial_url = initial_url
        self.setWindowTitle("browser")
        self.resize(1280, 820)

        try:
            self.config = json.loads(CONFIG_FILE.read_text())
        except Exception:
            self.config = {}
        try:
            self.history = json.loads(HISTORY_FILE.read_text())
        except Exception:
            self.history = []
        self.bridge = Bridge(self)

        # userscript plugins: *.user.js files next to the config
        # (Greasemonkey-style; Qt WebEngine can't run real extensions)
        self.plugins_dir = CONFIG_FILE.parent / "plugins"
        self.plugin_scripts = self._load_plugins()
        self.plugin_script_names = [s.name() for s in self.plugin_scripts]

        self.profile = self._make_profile("browser")
        self._perm_queue = []
        self._perm_widget = None
        self._session_perms = {}

        # top island bar: nav buttons + url bar
        self.urlbar = QLineEdit(objectName="urlbar")
        self.urlbar.setPlaceholderText("Search or enter address")
        self.urlbar.returnPressed.connect(self._navigate)

        # suggestions dropdown: domain guesses + Google search suggestions
        try:
            self.known_hosts = set(json.loads(HOSTS_FILE.read_text()))
        except Exception:
            self.known_hosts = set()
        self.suggest_model = QStringListModel(self)
        self.completer = QCompleter(self.suggest_model, self)
        self.completer.setCompletionMode(
            QCompleter.CompletionMode.UnfilteredPopupCompletion)
        self.urlbar.setCompleter(self.completer)
        self.completer.activated.connect(
            lambda _: QTimer.singleShot(0, self._navigate))
        self.completer.popup().setStyleSheet("""
            QListView {
                background: #0d0d12; color: #cdd6f4;
                border: 1px solid rgba(108, 112, 134, 110);
                border-radius: 10px; padding: 4px; outline: 0;
            }
            QListView::item { padding: 6px 10px; border-radius: 7px; }
            QListView::item:selected { background: #16161d; color: #ffffff; }
        """)
        self._nam = QNetworkAccessManager(self)
        self._suggest_reply = None
        self._suggest_timer = QTimer(self)
        self._suggest_timer.setSingleShot(True)
        self._suggest_timer.setInterval(150)
        self._suggest_timer.timeout.connect(self._fetch_suggestions)
        self.urlbar.textEdited.connect(lambda _t: self._suggest_timer.start())

        back = QToolButton(text="‹")
        fwd = QToolButton(text="›")
        reload_ = QToolButton(text="⟳")
        back.clicked.connect(lambda: self.current().back())
        fwd.clicked.connect(lambda: self.current().forward())
        reload_.clicked.connect(lambda: self.current().reload())

        translate = QToolButton(text="🌐")
        translate.setToolTip("Translate this page")
        translate.clicked.connect(self._translate_menu)
        self._translate_btn = translate

        proxybtn = QToolButton(text="📡")
        proxybtn.setToolTip("Proxy")
        proxybtn.clicked.connect(self._proxy_menu)
        self._proxy_btn = proxybtn

        bar = QHBoxLayout()
        bar.setContentsMargins(10, 8, 10, 2)
        bar.setSpacing(6)
        for w in (back, fwd, reload_):
            bar.addWidget(w)
        bar.addWidget(self.urlbar, 1)
        bar.addWidget(proxybtn)
        bar.addWidget(translate)

        self.tabs = TabWidget(self)
        self.tabs.setDocumentMode(True)
        self.tabs.setMovable(True)
        self.tabs.tabBar().tabMoved.connect(self._tab_moved)
        self.tabs.setElideMode(Qt.TextElideMode.ElideRight)
        self.tabs.currentChanged.connect(self._tab_changed)

        # Chrome-style tab groups: a colored name label sits in the tab
        # strip before its tabs; clicking it collapses/expands the group
        self.groups = []
        self.group_colors = {}
        self.collapsed = {}
        self.group_ids = {}
        self.group_profiles = {}
        self.group_sessions = {}
        self.sessions = [{"name": "Browser 1", "sid": "main"}]
        self.active_session = "main"
        self.session_profiles = {}
        self._book = QToolButton(text="📑", objectName="groupbtn")
        self._book.setToolTip("Tab groups")
        self._book.clicked.connect(self._group_menu)
        self.tabs.setCornerWidget(self._book, Qt.Corner.TopLeftCorner)
        # the + rides along right after the last tab, like Chrome
        self._newtab_btn = QToolButton(self.tabs.tabBar(), text="+",
                                       objectName="newtabbtn")
        self._newtab_btn.setToolTip("New tab")
        self._newtab_btn.setFixedSize(28, 26)
        self._newtab_btn.clicked.connect(lambda: self.new_tab())
        self._newtab_btn.show()
        self.tabs.tabBar().installEventFilter(self)

        self.chrome = QWidget(objectName="chrome")
        lay = QVBoxLayout(self.chrome)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        # virtual browsers: each entry up here is a full browser with
        # its own cookies and its own tabs
        self.sessrow = QWidget(objectName="sessrow")
        self.sesslay = QHBoxLayout(self.sessrow)
        self.sesslay.setContentsMargins(8, 4, 8, 0)
        self.sesslay.setSpacing(6)
        lay.addWidget(self.sessrow)
        lay.addLayout(bar)

        # download bar (hidden until a download starts)
        self.dlbar = QWidget(objectName="dlbar")
        self.dllay = QHBoxLayout(self.dlbar)
        self.dllay.setContentsMargins(10, 8, 10, 8)
        self.dllay.setSpacing(8)
        self.dllay.addStretch()
        self.dlbar.hide()

        root = QWidget()
        rlay = QVBoxLayout(root)
        rlay.setContentsMargins(0, 0, 0, 0)
        rlay.setSpacing(0)
        rlay.addWidget(self.chrome)
        rlay.addWidget(self.tabs, 1)
        rlay.addWidget(self.dlbar)
        self.setCentralWidget(root)

        for key, fn in {
            "Ctrl+T": self.new_tab,
            "Ctrl+W": lambda: self.close_tab(self.tabs.currentIndex()),
            "Ctrl+L": self._focus_url,
            "Ctrl+R": lambda: self.current().reload(),
            "F5": lambda: self.current().reload(),
            "Ctrl+Q": self.close,
            "Ctrl+Tab": lambda: self._cycle(1),
            "Ctrl+Shift+Tab": lambda: self._cycle(-1),
            "Shift+Tab": lambda: self._cycle_session(1),
            "F11": lambda: self.set_fullscreen(not self.isFullScreen()),
            "Ctrl+H": lambda: self.new_tab(url=HISTORY_PAGE.toString()),
            "F12": self.toggle_inspector,
            "Ctrl+Shift+I": self.toggle_inspector,
            "Ctrl+,": self.open_settings,
        }.items():
            QShortcut(QKeySequence(key), self).activated.connect(fn)

        self.bridge.updateFinished.connect(self._toast_result)
        QTimer.singleShot(3000, self._check_updates)
        self._toast = None

        # virtual browsers and groups survive restarts
        QApplication.instance().aboutToQuit.connect(self._save_groups)
        saved_sessions = [e for e in self.config.get("sessions", [])
                          if e.get("sid") and e.get("name")]
        if saved_sessions:
            self.sessions = saved_sessions
            if not any(e["sid"] == "main" for e in self.sessions):
                self.sessions.insert(0, {"name": "Browser 1", "sid": "main"})
        self.apply_proxy()
        self.active_session = self.sessions[0]["sid"]
        if self.config.get("restoreTabs", True):
            self._restore_groups()
            self._restore_session_tabs()
        self.new_tab(url=initial_url, group=None,
                     session=self.active_session)
        self.switch_session(self.active_session)

    def _restore_session_tabs(self):
        valid = {e["sid"] for e in self.sessions}
        for sid, items in (self.config.get("sessionTabs") or {}).items():
            if sid not in valid:
                continue
            for item in items:
                if isinstance(item, dict):
                    u, t = item.get("u", ""), item.get("t") or None
                else:
                    u, t = item, None
                if u:
                    self.new_tab(url=u, group=None, session=sid,
                                 switch=False, lazy=True, title=t)

    def _save_groups(self):
        data = []
        for g in self.groups:
            urls = []
            for i in self._group_indices(g):
                view = self.tabs.widget(i)
                url = view.url()
                if url == START_PAGE:
                    urls.append({"u": "", "t": ""})
                else:
                    urls.append({"u": url.toString()
                                 or getattr(view, "_pending", "")
                                 or getattr(view, "_requested", ""),
                                 "t": self.tabs.tabText(i)})
            data.append({"name": g,
                         "color": self.group_colors.get(g, "#6c7086"),
                         "collapsed": bool(self.collapsed.get(g)),
                         "gid": self.group_ids.get(g),
                         "session": self.group_sessions.get(g, "main"),
                         "urls": urls})
        self.config["tabGroups"] = data
        # loose tabs are saved per virtual browser too (start pages
        # excluded — every start spawns a fresh one anyway)
        session_tabs = {}
        for i in range(self.tabs.count()):
            view = self.tabs.widget(i)
            if self._is_header(view) or self._group_of(view) is not None:
                continue
            url = view.url()
            if url == START_PAGE:
                continue
            u = (url.toString() or getattr(view, "_pending", "")
                 or getattr(view, "_requested", ""))
            if not u:
                continue
            sid = getattr(view, "session", "main")
            session_tabs.setdefault(sid, []).append(
                {"u": u, "t": self.tabs.tabText(i)})
        self.config["sessionTabs"] = session_tabs
        self.config["sessions"] = self.sessions
        self.save_config()

    def _restore_groups(self):
        for entry in self.config.get("tabGroups", []):
            name = entry.get("name")
            urls = entry.get("urls", [])
            if not name or name in self.groups or not urls:
                continue
            if entry.get("gid"):
                self.group_ids[name] = entry["gid"]
            session = entry.get("session", "main")
            if not any(e["sid"] == session for e in self.sessions):
                session = "main"
            self._register_group(name, entry.get("color", "#6c7086"),
                                 session=session)
            for item in urls:
                if isinstance(item, dict):
                    u, t = item.get("u", ""), item.get("t") or None
                else:
                    u, t = item, None
                self.new_tab(url=u or None, group=name, switch=False,
                             lazy=bool(u), title=t)
            if entry.get("collapsed"):
                self._toggle_collapse(name)

    # ---- updates ----
    def _check_updates(self):
        """Quietly look for a newer version on GitHub at startup."""
        if not (APP_DIR / ".git").exists():
            return
        fetch = QProcess(self)
        fetch.setWorkingDirectory(str(APP_DIR))

        def fetched(*_):
            try:
                fetch.deleteLater()
            except RuntimeError:
                return  # quitting while the check was in flight
            self._count_behind()
        fetch.finished.connect(fetched)
        fetch.start("git", ["fetch", "--quiet"])

    def _count_behind(self):
        proc = QProcess(self)
        proc.setWorkingDirectory(str(APP_DIR))

        def done(*_):
            try:
                out = bytes(proc.readAllStandardOutput()).decode().strip()
                code = proc.exitCode()
                proc.deleteLater()
            except RuntimeError:
                return  # quitting while the check was in flight
            if code == 0 and out.isdigit() and int(out) > 0:
                self._show_toast()
        proc.finished.connect(done)
        proc.start("git", ["rev-list", "--count", "HEAD..@{u}"])

    def _show_toast(self):
        if self._toast:
            return
        toast = QWidget(self, objectName="toast")
        toast.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QHBoxLayout(toast)
        lay.setContentsMargins(14, 8, 8, 8)
        lay.setSpacing(10)
        self._toast_label = QLabel("Update available")
        update = QToolButton(text="Update now")
        close = QToolButton(text="\u2715", objectName="tabclose")
        lay.addWidget(self._toast_label)
        lay.addWidget(update)
        lay.addWidget(close)

        self._toast = toast
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.setInterval(5000)
        self._toast_timer.timeout.connect(self._hide_toast)

        close.clicked.connect(self._hide_toast)
        update.clicked.connect(lambda: (
            self._toast_timer.stop(),
            update.hide(),
            self._toast_label.setText("Updating\u2026"),
            self.bridge.runUpdate(),
        ))

        self._place_toast()
        toast.show()
        toast.raise_()
        self._toast_timer.start()

    def _place_toast(self):
        if self._toast:
            self._toast.adjustSize()
            self._toast.move(self.width() - self._toast.width() - 16, 54)

    def _hide_toast(self):
        if self._toast:
            self._toast_timer.stop()
            self._toast.deleteLater()
            self._toast = None

    def _toast_result(self, msg):
        if not self._toast:
            return
        self._toast_label.setText(msg)
        if msg.startswith("Updated"):
            restart = QToolButton(text="Restart now")
            restart.clicked.connect(self.restart)
            self._toast.layout().insertWidget(1, restart)
            self._toast_timer.stop()  # stays until acted on or dismissed
        else:
            self._toast_timer.setInterval(8000)
            self._toast_timer.start()
        self._place_toast()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_toast()
        self._place_perm()

    # ---- tabs ----
    def current(self):
        return self.tabs.currentWidget()

    def new_tab(self, url=None, switch=True, blank=False,
                group=INHERIT_GROUP, session=None, lazy=False, title=None):
        if group is INHERIT_GROUP:
            group = self._group_of(self.current())
        if session is None:
            session = (self.group_sessions.get(group)
                       if group is not None else self.active_session)
        view = WebView(self, self._profile_for(group, session))
        view.setZoomFactor(float(self.config.get("zoom", 1.0)))
        view.group = group
        view.session = session or "main"
        view.urlChanged.connect(lambda u, v=view: self._url_changed(v, u))
        view.titleChanged.connect(lambda t, v=view: self._title_changed(v, t))
        view.iconChanged.connect(lambda ic, v=view: self._icon_changed(v, ic))
        if group is not None:
            if self.collapsed.get(group):
                self._toggle_collapse(group)
            block = [self._header_index(group)] + self._group_indices(group)
            i = self.tabs.insertTab(max(block) + 1, view, "New tab")
        else:
            i = self.tabs.addTab(view, "New tab")

        self._add_close_button(i, view)

        if switch:
            self.tabs.setCurrentIndex(i)
        if not blank:
            if url is None:
                view.load(START_PAGE)
                self._focus_url()
            elif lazy:
                # the page loads only when the tab is first opened,
                # so restored sessions cost no memory until used
                view._pending = url
                view._requested = url
            else:
                view._requested = url  # fallback for saving before commit
                view.load(QUrl(url))
        if title:
            self.tabs.setTabText(i, title)
        elif lazy and url:
            self.tabs.setTabText(i, QUrl(url).host() or "Tab")
        return view

    def _add_close_button(self, index, view):
        close = QToolButton(text="✕", objectName="tabclose")
        close.clicked.connect(lambda _, v=view: self.close_tab(self.tabs.indexOf(v)))
        # wrapper centers the circle between the tab text and the tab's right wall
        holder = QWidget()
        hl = QHBoxLayout(holder)
        hl.setContentsMargins(0, 0, 6, 0)
        hl.addWidget(close)
        self.tabs.tabBar().setTabButton(index, QTabBar.ButtonPosition.RightSide, holder)

    def close_tab(self, index):
        w = self.tabs.widget(index)
        if w is None or self._is_header(w):
            return
        group = self._group_of(w)
        self.tabs.removeTab(index)
        w.deleteLater()
        # a group whose last tab closes disappears, like in Chrome
        if group is not None and not self._group_indices(group):
            h = self._header_index(group)
            if h is not None:
                hw = self.tabs.widget(h)
                self.tabs.removeTab(h)
                hw.deleteLater()
            self.groups.remove(group)
            self.group_colors.pop(group, None)
            self.collapsed.pop(group, None)
        self._ensure_tab_or_quit()

    def _cycle(self, step):
        # skip group headers and collapsed (hidden) tabs
        bar = self.tabs.tabBar()
        n = self.tabs.count()
        i = self.tabs.currentIndex()
        for _ in range(n):
            i = (i + step) % n
            if bar.isTabVisible(i) and not self._is_header(self.tabs.widget(i)):
                self.tabs.setCurrentIndex(i)
                return

    # ---- drag & drop between groups ----
    def _tab_moved(self, _frm, _to):
        """While a tab is dragged, its group follows its position:
        inside a group's block (or onto its pill) joins it, outside
        leaves. Qt reports every displaced tab here, so only the tab
        actually held by the user is ever reassigned."""
        if getattr(self, "_fixing", False):
            return
        w = getattr(self, "_drag_view", None)
        if w is None:
            return
        to = self.tabs.indexOf(w)
        if to < 0:
            return
        left = self.tabs.widget(to - 1) if to > 0 else None
        right = (self.tabs.widget(to + 1)
                 if to + 1 < self.tabs.count() else None)
        if left is None:
            lg = None
        elif self._is_header(left):
            lg = left.group_header
        else:
            lg = getattr(left, "group", None)
        if right is not None and self._is_header(right):
            # dropped onto the pill: merge into that group
            target = right.group_header
        else:
            rg = None if right is None else getattr(right, "group", None)
            target = lg if lg is not None and lg == rg else None
        if target is not None and self.collapsed.get(target):
            target = None  # no dropping into a folded group
        w.group = target
        self.tabs.tabBar().update()

    def _fix_group_layout(self, group):
        """Ensure the group's tabs sit contiguously after its pill."""
        bar = self.tabs.tabBar()
        for _ in range(self.tabs.count()):
            h = self._header_index(group)
            members = self._group_indices(group)
            if h is None or not members:
                return
            want = set(range(h + 1, h + 1 + len(members)))
            misplaced = [m for m in members if m not in want]
            if not misplaced:
                return
            m = misplaced[0]
            bar.moveTab(m, h + len(members) if m > h else h)

    def _finalize_drag(self):
        held = self.current()  # the tab the user was dragging stays active
        self._fixing = True
        try:
            for g in list(self.groups):
                self._fix_group_layout(g)
        finally:
            self._fixing = False
        for g in list(self.groups):
            self._cleanup_group_if_empty(g)
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if not self._is_header(w):
                self._sync_profile(w)
        if held is not None:
            i = self.tabs.indexOf(held)
            if i >= 0 and not self._is_header(held):
                self.tabs.setCurrentIndex(i)
        self.tabs.tabBar().update()

    # ---- translation ----
    def _translate_menu(self):
        menu = QMenu(self)
        current = self.config.get("translateLang", "de")

        search = QLineEdit(menu)
        search.setPlaceholderText("Search language\u2026")
        search.setStyleSheet(
            "QLineEdit { background: #000000; color: #cdd6f4;"
            " border: 1px solid rgba(108, 112, 134, 110);"
            " border-radius: 0px; padding: 6px 10px; margin: 2px 4px; }")
        box = QWidgetAction(menu)
        box.setDefaultWidget(search)
        menu.addAction(box)

        entries = []
        for code, name in LANGUAGES:
            mark = "\u2713 " if code == current else "    "
            action = menu.addAction(mark + name)
            action.triggered.connect(
                lambda _, c=code: self._translate_page(c))
            haystack = " ".join((name.lower(), code.lower(),
                                 LANGUAGE_ALIASES.get(code, "")))
            entries.append((action, haystack))

        def apply_filter(text):
            needle = text.strip().lower()
            for action, haystack in entries:
                action.setVisible(needle in haystack)
        search.textChanged.connect(apply_filter)
        search.returnPressed.connect(lambda: next(
            (a.trigger() or menu.close()
             for a, _h in entries if a.isVisible()), None))
        menu.aboutToShow.connect(search.setFocus)
        self._tmenu = menu  # kept for tests
        menu.exec(self._translate_btn.mapToGlobal(
            self._translate_btn.rect().bottomLeft()))

    def _translate_page(self, lang):
        self.config["translateLang"] = lang
        self.save_config()
        self.apply_language()
        view = self.current()
        if view is None:
            return
        url = view.url()
        if url.scheme() not in ("http", "https"):
            return
        target = QUrl("https://translate.google.com/translate")
        q = QUrlQuery()
        q.addQueryItem("sl", "auto")
        q.addQueryItem("tl", lang)
        q.addQueryItem("u", url.toString())
        target.setQuery(q)
        view.load(target)

    # ---- virtual browsers ----
    def _cycle_session(self, step):
        """Shift+Tab hops to the next virtual browser."""
        if len(self.sessions) < 2:
            return
        sids = [e["sid"] for e in self.sessions]
        i = sids.index(self.active_session) if self.active_session in sids else 0
        self.switch_session(sids[(i + step) % len(sids)])

    def _update_session_bar(self):
        lay = self.sesslay
        while lay.count():
            item = lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        # also sweep strays a drag left floating outside the layout
        for child in self.sessrow.children():
            if isinstance(child, QWidget):
                child.hide()
                child.deleteLater()
        for entry in self.sessions:
            active = entry["sid"] == self.active_session
            b = QToolButton(text=entry["name"])
            b.setStyleSheet(
                "QToolButton { background: %s; color: %s; border: 1px solid %s;"
                " border-radius: 0px; padding: 4px 14px; font-weight: %s; }"
                % (("#16161d", "#ffffff", "#a6adc8", "bold") if active
                   else ("#0d0d12", "#6c7086", "rgba(108, 112, 134, 60)", "normal")))
            b.clicked.connect(lambda _, sid=entry["sid"]: self.switch_session(sid))
            b.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            b.customContextMenuRequested.connect(
                lambda _p, sid=entry["sid"], b=b: self._session_menu(b, sid))
            b._session_sid = entry["sid"]
            b.installEventFilter(self)
            lay.addWidget(b)
        plus = QToolButton(text="+")
        plus.setToolTip("New virtual browser (own cookies and tabs)")
        plus.setStyleSheet("QToolButton { background: #0d0d12; color: #6c7086;"
                           " border: 1px solid rgba(108, 112, 134, 60);"
                           " border-radius: 0px; padding: 4px 10px; }")
        plus.clicked.connect(self._add_session)
        lay.addWidget(plus)
        lay.addStretch()

    def switch_session(self, sid):
        self.active_session = sid
        bar = self.tabs.tabBar()
        first = None
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            in_session = getattr(w, "session", "main") == sid
            if self._is_header(w):
                visible = in_session
            else:
                g = getattr(w, "group", None)
                visible = in_session and not (g and self.collapsed.get(g))
            bar.setTabVisible(i, visible)
            if visible and not self._is_header(w) and first is None:
                first = i
        self._update_session_bar()
        current = self.current()
        if (current is None or self._is_header(current)
                or getattr(current, "session", "main") != sid):
            if first is not None:
                self.tabs.setCurrentIndex(first)
            else:
                self.new_tab(group=None)  # fresh, ungrouped, this browser
        bar.update()

    def _add_session(self):
        names = {e["name"] for e in self.sessions}
        n = 2
        while "Browser %d" % n in names:
            n += 1
        name, ok = QInputDialog.getText(
            self, "New browser", "Name:", text="Browser %d" % n)
        name = name.strip()
        if not ok or not name:
            return
        while name in names:
            name += " 2"
        self.sessions.append({"name": name, "sid": uuid.uuid4().hex[:8]})
        self.switch_session(self.sessions[-1]["sid"])

    def _session_buttons_in_layout(self):
        out = []
        for k in range(self.sesslay.count()):
            w = self.sesslay.itemAt(k).widget()
            if w is not None and hasattr(w, "_session_sid"):
                out.append(w)
        return out

    def _drag_session_move(self, local_x):
        drag = self._sess_drag
        btn = drag["btn"]
        if not drag["moved"]:
            if abs(local_x - drag["x"]) <= 12:
                return
            # lift the button out of the row; a spacer keeps its slot
            drag["moved"] = True
            drag["index"] = self._session_buttons_in_layout().index(btn)
            spacer = QWidget(self.sessrow)
            spacer.setFixedSize(btn.size())
            drag["spacer"] = spacer
            self.sesslay.removeWidget(btn)
            self.sesslay.insertWidget(drag["index"], spacer)
            spacer.show()
        # the button follows the cursor (all math in strip coordinates)
        x = int(local_x - drag["grip"])
        x = max(0, min(x, self.sessrow.width() - btn.width()))
        btn.move(x, btn.y())
        btn.raise_()
        # the gap travels as the cursor crosses neighbors
        others = self._session_buttons_in_layout()
        target = sum(1 for b in others
                     if local_x > b.geometry().center().x())
        if target != drag["index"]:
            drag["index"] = target
            self.sesslay.removeWidget(drag["spacer"])
            self.sesslay.insertWidget(target, drag["spacer"])
            self.sesslay.activate()

    def _drag_session_drop(self, drag):
        drag["btn"].hide()
        drag["btn"].deleteLater()  # the rebuild recreates it in place
        spacer = drag["spacer"]
        if spacer is not None:
            self.sesslay.removeWidget(spacer)
            spacer.deleteLater()
        sid = drag["btn"]._session_sid
        entry = next((e for e in self.sessions if e["sid"] == sid), None)
        if entry is not None:
            rest = [e for e in self.sessions if e["sid"] != sid]
            i = max(0, min(drag["index"], len(rest)))
            self.sessions = rest[:i] + [entry] + rest[i:]
        self._update_session_bar()

    def _session_menu(self, button, sid):
        menu = QMenu(self)
        name = next((e["name"] for e in self.sessions if e["sid"] == sid), sid)
        rename = menu.addAction("Rename\u2026")
        close = menu.addAction("Close \u201c%s\u201d" % name)
        close.setEnabled(len(self.sessions) > 1)
        chosen = menu.exec(button.mapToGlobal(button.rect().bottomLeft()))
        if chosen is close:
            self._close_session(sid)
        elif chosen is rename:
            new, ok = QInputDialog.getText(
                self, "Rename browser", "Name:", text=name)
            new = new.strip()
            if ok and new and all(e["name"] != new for e in self.sessions):
                for entry in self.sessions:
                    if entry["sid"] == sid:
                        entry["name"] = new
                self._update_session_bar()

    def _close_session(self, sid):
        if len(self.sessions) <= 1:
            return
        for i in reversed(range(self.tabs.count())):
            w = self.tabs.widget(i)
            if getattr(w, "session", "main") == sid:
                self.tabs.removeTab(i)
                w.deleteLater()
        for g in [g for g, s in list(self.group_sessions.items()) if s == sid]:
            if g in self.groups:
                self.groups.remove(g)
            self.group_colors.pop(g, None)
            self.collapsed.pop(g, None)
            self.group_ids.pop(g, None)
            self.group_sessions.pop(g, None)
        self.sessions = [e for e in self.sessions if e["sid"] != sid]
        self.session_profiles.pop(sid, None)
        if self.active_session == sid:
            self.switch_session(self.sessions[0]["sid"])
        else:
            self._update_session_bar()

    # ---- site permissions (microphone, camera, screen share) ----
    def _permission_requested(self, permission):
        label = PERMISSION_LABELS.get(permission.permissionType())
        if label is None:
            return  # let the engine keep its default for exotic requests
        origin = permission.origin().host() or permission.origin().toString()
        key = "%s|%s" % (origin, permission.permissionType().name)
        if self.config.get("permissions", {}).get(key):
            permission.grant()
            return
        if key in self._session_perms:
            permission.grant() if self._session_perms[key] else permission.deny()
            return
        self._perm_queue.append((permission, origin, label, key))
        self._next_permission()

    def _next_permission(self):
        if self._perm_widget is not None or not self._perm_queue:
            return
        permission, origin, label, key = self._perm_queue.pop(0)
        # a small card in the bottom-right corner, clear of the tabs
        card = QWidget(self, objectName="permcard")
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card.setFixedWidth(300)
        v = QVBoxLayout(card)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(12)
        msg = QLabel("%s wants to %s." % (origin, label))
        msg.setWordWrap(True)
        v.addWidget(msg)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addStretch()
        deny = QToolButton(text="Deny")
        allow = QToolButton(text="Allow", objectName="permallow")
        row.addWidget(deny)
        row.addWidget(allow)
        v.addLayout(row)
        self._perm_widget = card

        def decide(granted):
            permission.grant() if granted else permission.deny()
            self._session_perms[key] = granted
            if granted:  # only allows are remembered across restarts
                self.config.setdefault("permissions", {})[key] = True
                self.save_config()
            card.deleteLater()
            self._perm_widget = None
            self._next_permission()

        allow.clicked.connect(lambda: decide(True))
        deny.clicked.connect(lambda: decide(False))
        self._place_perm()
        card.show()
        card.raise_()

    def _place_perm(self):
        card = getattr(self, "_perm_widget", None)
        if card is not None:
            card.adjustSize()
            card.move(self.width() - card.width() - 18,
                      self.height() - card.height() - 18)

    # ---- tab groups (Chrome-style inline headers) ----
    def _group_of(self, widget):
        if widget is None or self._is_header(widget):
            return None
        return getattr(widget, "group", None)

    def _is_header(self, widget):
        return getattr(widget, "group_header", None) is not None

    def _header_index(self, group):
        for i in range(self.tabs.count()):
            if getattr(self.tabs.widget(i), "group_header", None) == group:
                return i
        return None

    def _group_indices(self, group):
        return [i for i in range(self.tabs.count())
                if not self._is_header(self.tabs.widget(i))
                and getattr(self.tabs.widget(i), "group", None) == group]

    def _group_dot(self, group):
        pix = QPixmap(12, 12)
        pix.fill(QColor(self.group_colors.get(group, "#6c7086")))
        return QIcon(pix)

    def _group_menu(self):
        menu = GroupMenu(self)
        listed = [g for g in self.groups
                  if self.group_sessions.get(g, "main") == self.active_session]
        for g in listed:
            action = menu.addAction(self._group_dot(g), g)
            action.setData(g)
            action.triggered.connect(lambda _, g=g: self._goto_group(g))
        if listed:
            menu.addSeparator()
        menu.addAction("New group\u2026").triggered.connect(self._new_group)
        menu.exec(self._book.mapToGlobal(self._book.rect().bottomLeft()))

    def _prompt_group(self):
        """Ask for a name and color; returns (name, color) or None."""
        name, ok = QInputDialog.getText(self, "New group", "Group name:")
        name = name.strip()
        if not ok or not name or name in self.groups:
            return None
        picker = QMenu(self)
        for label, color in GROUP_COLORS:
            pix = QPixmap(12, 12)
            pix.fill(QColor(color))
            picker.addAction(QIcon(pix), label).setData(color)
        chosen = picker.exec(
            self._book.mapToGlobal(self._book.rect().bottomLeft()))
        fallback = GROUP_COLORS[len(self.groups) % len(GROUP_COLORS)][1]
        return name, (chosen.data() if chosen else fallback)

    def _register_group(self, name, color, at=None, session=None):
        self.groups.append(name)
        self.group_colors[name] = color
        self.collapsed[name] = False
        session = session or self.active_session
        self.group_sessions[name] = session
        header = QWidget()
        header.group_header = name
        header.session = session
        if at is None:
            self.tabs.addTab(header, name)
        else:
            self.tabs.insertTab(at, header, name)
        self.tabs.tabBar().update()

    def _new_group(self):
        result = self._prompt_group()
        if result is None:
            return
        self._register_group(*result)
        self.new_tab(group=result[0])  # every group starts with a fresh tab

    def _tab_to_new_group(self, index):
        result = self._prompt_group()
        if result is None:
            return
        view = self.tabs.widget(index)
        self._register_group(*result, at=index)  # header lands before the tab
        view.group = result[0]
        self._sync_profile(view)
        self.tabs.tabBar().update()

    def _move_tab_to_group(self, index, group):
        view = self.tabs.widget(index)
        old = self._group_of(view)
        if old == group:
            return
        title = self.tabs.tabText(index)
        was_current = view is self.current()
        self.tabs.removeTab(index)
        view.group = group
        if group is not None:
            if self.collapsed.get(group):
                self._toggle_collapse(group)
            block = [self._header_index(group)] + self._group_indices(group)
            j = self.tabs.insertTab(max(block) + 1, view, title)
        else:
            j = self.tabs.addTab(view, title)
        self.tabs.setTabIcon(j, view.icon())
        self._add_close_button(j, view)
        self._sync_profile(view)
        if was_current:
            self.tabs.setCurrentIndex(j)
        if old is not None:
            self._cleanup_group_if_empty(old)
        self.tabs.tabBar().update()

    def _cleanup_group_if_empty(self, group):
        if self._group_indices(group):
            return
        h = self._header_index(group)
        if h is not None:
            hw = self.tabs.widget(h)
            self.tabs.removeTab(h)
            hw.deleteLater()
        if group in self.groups:
            self.groups.remove(group)
        self.group_colors.pop(group, None)
        self.collapsed.pop(group, None)

    def _rename_group(self, old, new):
        new = new.strip()
        if not new or new in self.groups or old not in self.groups:
            return
        for i in self._group_indices(old):
            self.tabs.widget(i).group = new
        h = self._header_index(old)
        if h is not None:
            self.tabs.widget(h).group_header = new
            self.tabs.setTabText(h, new)
        self.groups[self.groups.index(old)] = new
        self.group_colors[new] = self.group_colors.pop(old, "#6c7086")
        self.collapsed[new] = self.collapsed.pop(old, False)
        if old in self.group_ids:
            self.group_ids[new] = self.group_ids.pop(old)
        self.tabs.tabBar().update()

    def ungroup(self, group):
        """Dissolve the group but keep its tabs, like Chrome's Ungroup."""
        if self.collapsed.get(group):
            self._toggle_collapse(group)
        for i in self._group_indices(group):
            member = self.tabs.widget(i)
            member.group = None
            self._sync_profile(member)
        h = self._header_index(group)
        if h is not None:
            hw = self.tabs.widget(h)
            self.tabs.removeTab(h)
            hw.deleteLater()
        if group in self.groups:
            self.groups.remove(group)
        self.group_colors.pop(group, None)
        self.collapsed.pop(group, None)
        self.tabs.tabBar().update()

    def _tab_menu(self, index):
        view = self.tabs.widget(index)
        group = self._group_of(view)
        menu = QMenu(self)
        if group is None:
            menu.addAction("Add tab to new group\u2026").triggered.connect(
                lambda: self._tab_to_new_group(self.tabs.indexOf(view)))
            if self.groups:
                sub = menu.addMenu("Add tab to group")
                for g in self.groups:
                    sub.addAction(self._group_dot(g), g).triggered.connect(
                        lambda _, g=g: self._move_tab_to_group(
                            self.tabs.indexOf(view), g))
        else:
            menu.addAction("New tab in group").triggered.connect(
                lambda: self.new_tab(group=group))
            menu.addAction("Remove from group").triggered.connect(
                lambda: self._move_tab_to_group(self.tabs.indexOf(view), None))
        menu.addSeparator()
        menu.addAction("Close tab").triggered.connect(
            lambda: self.close_tab(self.tabs.indexOf(view)))
        bar = self.tabs.tabBar()
        menu.exec(bar.mapToGlobal(bar.tabRect(index).bottomLeft()))

    def _header_menu(self, index):
        group = self.tabs.widget(index).group_header
        menu = QMenu(self)
        menu.addAction("New tab in group").triggered.connect(
            lambda: self.new_tab(group=group))
        menu.addAction("Rename\u2026").triggered.connect(
            lambda: self._rename_dialog(group))
        colors = menu.addMenu("Color")
        for label, color in GROUP_COLORS:
            pix = QPixmap(12, 12)
            pix.fill(QColor(color))
            colors.addAction(QIcon(pix), label).triggered.connect(
                lambda _, c=color: self._set_group_color(group, c))
        menu.addSeparator()
        menu.addAction("Ungroup").triggered.connect(
            lambda: self.ungroup(group))
        menu.addAction("Close group").triggered.connect(
            lambda: self.delete_group(group))
        bar = self.tabs.tabBar()
        menu.exec(bar.mapToGlobal(bar.tabRect(index).bottomLeft()))

    def _rename_dialog(self, group):
        name, ok = QInputDialog.getText(
            self, "Rename group", "Group name:", text=group)
        if ok:
            self._rename_group(group, name)

    def _set_group_color(self, group, color):
        if group in self.group_colors:
            self.group_colors[group] = color
            self.tabs.tabBar().update()

    def _goto_group(self, group):
        if self.collapsed.get(group):
            self._toggle_collapse(group)
        members = self._group_indices(group)
        if members:
            self.tabs.setCurrentIndex(members[0])

    def _toggle_collapse(self, group):
        self.collapsed[group] = not self.collapsed.get(group, False)
        bar = self.tabs.tabBar()
        for i in self._group_indices(group):
            bar.setTabVisible(i, not self.collapsed[group])

    def _nearest_tab(self, index):
        bar = self.tabs.tabBar()
        order = list(range(index + 1, self.tabs.count()))
        order += list(range(index - 1, -1, -1))
        for i in order:
            if bar.isTabVisible(i) and not self._is_header(self.tabs.widget(i)):
                return i
        return None

    def delete_group(self, group):
        """Close the group's tabs and its header."""
        for i in reversed(self._group_indices(group)):
            w = self.tabs.widget(i)
            self.tabs.removeTab(i)
            w.deleteLater()
        h = self._header_index(group)
        if h is not None:
            hw = self.tabs.widget(h)
            self.tabs.removeTab(h)
            hw.deleteLater()
        if group in self.groups:
            self.groups.remove(group)
        self.group_colors.pop(group, None)
        self.collapsed.pop(group, None)
        self._ensure_tab_or_quit()

    def _ensure_tab_or_quit(self):
        """Closing the very last tab closes the browser, like Chrome.
        Other virtual browsers keep this one alive with a fresh tab;
        tabs surviving only in folded groups unfold instead."""
        real = [i for i in range(self.tabs.count())
                if not self._is_header(self.tabs.widget(i))]
        if not real:
            self.close()
            return
        mine = [i for i in real
                if getattr(self.tabs.widget(i), "session", "main")
                == self.active_session]
        if not mine:
            self.new_tab(group=None)
            return
        bar = self.tabs.tabBar()
        if not any(bar.isTabVisible(i) for i in mine):
            for g in self.groups:
                if (self.collapsed.get(g)
                        and self.group_sessions.get(g, "main")
                        == self.active_session):
                    self._toggle_collapse(g)
                    members = self._group_indices(g)
                    if members:
                        self.tabs.setCurrentIndex(members[0])
                    break

    # ---- navigation ----
    def _navigate(self):
        text = self.urlbar.text().strip()
        if not text:
            return
        if " " in text or ("." not in text and text != "localhost"):
            engine = SEARCH_ENGINES.get(self.config.get("searchEngine", "google"),
                                        SEARCH_ENGINES["google"])
            url = engine[1].format(QUrl.toPercentEncoding(text).data().decode())
        elif "://" in text:
            url = text
        else:
            url = "https://" + text
        self.current().load(QUrl(url))
        self.current().setFocus()

    def _focus_url(self):
        self.urlbar.setFocus()
        self.urlbar.selectAll()

    # ---- suggestions ----
    def _fetch_suggestions(self):
        text = self.urlbar.text().strip().lower()
        if len(text) < 2 or "://" in text or not self.urlbar.hasFocus():
            return
        domains = [d for d in COMMON_SITES + sorted(self.known_hosts)
                   if d.startswith(text) or d.split(".")[0].startswith(text)
                   or d.startswith("www." + text)]
        domains = list(dict.fromkeys(domains))
        domains = [d for d in domains
                   if not (d.startswith("www.") and d[4:] in domains)][:3]
        if self._suggest_reply is not None:
            self._suggest_reply.abort()
        url = QUrl(SUGGEST_URL)
        q = QUrlQuery()
        q.addQueryItem("client", "firefox")
        q.addQueryItem("q", text)
        url.setQuery(q)
        reply = self._nam.get(QNetworkRequest(url))
        self._suggest_reply = reply
        reply.finished.connect(
            lambda r=reply, t=text, d=domains: self._got_suggestions(r, t, d))

    def _got_suggestions(self, reply, text, domains):
        if reply is self._suggest_reply:
            self._suggest_reply = None
        searches = []
        try:
            searches = json.loads(bytes(reply.readAll()).decode())[1]
        except Exception:
            pass
        reply.deleteLater()
        if self.urlbar.text().strip().lower() != text:
            return  # user typed on; a newer request is coming
        items = domains + [s for s in searches if s not in domains][:6]
        self.suggest_model.setStringList(items)
        if items and self.urlbar.hasFocus():
            self.completer.complete()

    def _remember_host(self, url):
        host = url.host()
        if url.scheme() in ("http", "https") and host and host not in self.known_hosts:
            self.known_hosts.add(host)
            try:
                HOSTS_FILE.parent.mkdir(parents=True, exist_ok=True)
                HOSTS_FILE.write_text(json.dumps(sorted(self.known_hosts)))
            except OSError:
                pass

    def _url_changed(self, view, url):
        self._remember_host(url)
        host = url.host().removeprefix("www.")
        # our own pages (start/settings/history) are already dark by
        # design — force-dark would invert their white toggles to gray
        own_page = url.scheme() == "file"
        native_dark = (own_page
                       or any(host == d or host.endswith("." + d)
                              for d in NATIVE_DARK_SITES)
                       or bool(re.fullmatch(r"google\.[a-z.]+", host)))
        view.page().settings().setAttribute(
            QWebEngineSettings.WebAttribute.ForceDarkMode,
            bool(self.config.get("forceDark", True)) and not native_dark)
        # never clobber the bar while the user is typing in it
        if view is self.current() and not self.urlbar.hasFocus():
            self.urlbar.setText("" if url == START_PAGE else url.toString())
            self.urlbar.setCursorPosition(0)

    def _place_newtab(self):
        btn = getattr(self, "_newtab_btn", None)
        if btn is None:
            return
        bar = self.tabs.tabBar()
        last = None
        for i in range(self.tabs.count()):
            if bar.isTabVisible(i):
                last = i
        x = 6 if last is None else bar.tabRect(last).right() + 6
        x = min(x, bar.width() - btn.width() - 2)
        y = max(0, (bar.height() - btn.height()) // 2)
        btn.move(max(0, x), y)
        btn.raise_()

    def _update_close_buttons(self):
        """Very small tabs show just the site icon: the close button
        survives only on the active tab, like Chrome."""
        bar = self.tabs.tabBar()
        current = self.tabs.currentIndex()
        for i in range(self.tabs.count()):
            holder = bar.tabButton(i, QTabBar.ButtonPosition.RightSide)
            if holder is None:
                continue
            want = bar.tabRect(i).width() >= 90 or i == current
            if holder.isVisibleTo(bar) != want:
                holder.setVisible(want)

    def _icon_changed(self, view, icon):
        i = self.tabs.indexOf(view)
        if i >= 0:
            self.tabs.setTabIcon(i, icon)

    def _title_changed(self, view, title):
        i = self.tabs.indexOf(view)
        if i >= 0:
            self.tabs.setTabText(i, title or "New tab")
            self.tabs.setTabToolTip(i, title)
        self._record_history(view.url(), title)

    # ---- history ----
    def _record_history(self, url, title):
        if not self.config.get("history", True):
            return
        if url.scheme() not in ("http", "https") or not title:
            return
        entry = {"url": url.toString(), "title": title, "t": int(time.time())}
        if self.history and self.history[-1]["url"] == entry["url"]:
            self.history[-1] = entry  # same page: refresh title/time only
        else:
            self.history.append(entry)
            if len(self.history) > HISTORY_MAX:
                del self.history[:len(self.history) - HISTORY_MAX + 500]
        self.save_history()

    def save_history(self):
        try:
            HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            HISTORY_FILE.write_text(json.dumps(self.history))
        except OSError:
            pass

    def save_config(self):
        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_FILE.write_text(json.dumps(self.config))
        except OSError:
            pass

    def eventFilter(self, obj, event):
        # dragging a virtual-browser button: it lifts out of the row
        # and floats with the cursor, a gap marks where it will land
        if isinstance(obj, QToolButton) and hasattr(obj, "_session_sid"):
            if (event.type() == QEvent.Type.MouseButtonPress
                    and event.button() == Qt.MouseButton.LeftButton):
                local = self.sessrow.mapFromGlobal(
                    event.globalPosition().toPoint()).x()
                self._sess_drag = {"btn": obj, "moved": False,
                                   "x": local,
                                   "grip": event.position().x(),
                                   "spacer": None, "index": 0}
            elif (event.type() == QEvent.Type.MouseMove
                    and getattr(self, "_sess_drag", None)):
                self._drag_session_move(self.sessrow.mapFromGlobal(
                    event.globalPosition().toPoint()).x())
            elif (event.type() == QEvent.Type.MouseButtonRelease
                    and getattr(self, "_sess_drag", None)):
                drag = self._sess_drag
                self._sess_drag = None
                if drag["moved"]:
                    self._drag_session_drop(drag)
                    return True  # a drag is not a click
            return False
        # group headers act as fold/unfold buttons: swallow their clicks
        # before Qt selects them, so the page never flashes
        if (obj is self.tabs.tabBar()
                and event.type() in (QEvent.Type.MouseButtonPress,
                                     QEvent.Type.MouseButtonDblClick)):
            i = obj.tabAt(event.position().toPoint())
            if event.type() == QEvent.Type.MouseButtonPress:
                self._drag_active = True
                w0 = self.tabs.widget(i) if i >= 0 else None
                # remember which tab the hand is on: during a drag Qt
                # also reports the tabs being pushed aside, and only the
                # held tab may change group membership
                self._drag_view = (w0 if w0 is not None
                                   and not self._is_header(w0) else None)
            if i >= 0:
                w = self.tabs.widget(i)
                if event.button() == Qt.MouseButton.RightButton:
                    if self._is_header(w):
                        self._header_menu(i)
                    else:
                        self._tab_menu(i)
                    return True
                if self._is_header(w):
                    if event.button() == Qt.MouseButton.LeftButton:
                        self._header_clicked(w.group_header, i)
                    return True
        if (obj is self.tabs.tabBar()
                and event.type() == QEvent.Type.MouseButtonRelease
                and getattr(self, "_drag_active", False)):
            self._drag_active = False
            self._drag_view = None
            QTimer.singleShot(0, self._finalize_drag)
        return super().eventFilter(obj, event)

    def _tab_changed(self, index):
        w = self.tabs.widget(index)
        if w is not None and self._is_header(w):
            # selection landed on a header some indirect way: step off it
            QTimer.singleShot(0, lambda: self._step_off_header(index))
            return
        if w is not None and getattr(w, "_pending", None):
            pending = w._pending
            w._pending = None
            w.load(QUrl(pending))
        if w is not None and hasattr(w, "url"):
            url = w.url()
            self.urlbar.setText("" if url == START_PAGE else url.toString())
        self._update_close_buttons()

    def _step_off_header(self, index):
        # only act if the selection is still stuck on that header
        w = self.tabs.widget(index)
        if (self.tabs.currentIndex() != index or w is None
                or not self._is_header(w)):
            return
        target = self._nearest_tab(index)
        if target is not None:
            self.tabs.setCurrentIndex(target)

    def _header_clicked(self, group, index):
        bar = self.tabs.tabBar()
        if not self.collapsed.get(group, False):
            # about to collapse: leave the group BEFORE its tabs hide,
            # otherwise Qt momentarily selects the header (flash)
            cur = self.tabs.currentIndex()
            if self._group_of(self.tabs.widget(cur)) == group:
                outside = [i for i in range(self.tabs.count())
                           if bar.isTabVisible(i)
                           and not self._is_header(self.tabs.widget(i))
                           and self._group_of(self.tabs.widget(i)) != group]
                if outside:
                    self.tabs.setCurrentIndex(
                        min(outside, key=lambda i: abs(i - cur)))
                else:
                    self.new_tab(group=None)  # fresh ungrouped tab
        self._toggle_collapse(group)

    # ---- misc ----
    def set_fullscreen(self, on):
        self.chrome.setVisible(not on)
        self.tabs.tabBar().setVisible(not on)
        self.showFullScreen() if on else self.showNormal()

    def _make_profile(self, storage):
        """A fully configured cookie jar; each tab group gets its own."""
        profile = QWebEngineProfile(storage, self)
        profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        profile.downloadRequested.connect(self._download)
        s = profile.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)
        # the start page is a local file; without this it may not navigate
        # to the web (search box / quick links -> ERR_NETWORK_ACCESS_DENIED)
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        # let calls ring and voice chats start without a prior click
        s.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        # auto-darken pages that have no dark theme of their own
        s.setAttribute(QWebEngineSettings.WebAttribute.ForceDarkMode,
                       bool(self.config.get("forceDark", True)))
        # some sites (Teams…) block calls on unknown browsers; the engine
        # IS Chromium, so drop the QtWebEngine token from the identity
        profile.setHttpUserAgent(
            re.sub(r"\s?QtWebEngine/[\d.]+", "", profile.httpUserAgent()))
        lang = self.config.get("translateLang", "de")
        profile.setHttpAcceptLanguage(
            lang if lang.startswith("en") else lang + ",en")
        profile.settings().setFontSize(
            QWebEngineSettings.FontSize.MinimumFontSize,
            int(self.config.get("minFont", 0) or 0))
        profile.scripts().insert(self._google_script())
        for script in self.plugin_scripts:
            profile.scripts().insert(script)
        return profile

    def _google_script(self):
        script = QWebEngineScript()
        script.setName("google-mode")
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
        script.setWorldId(QWebEngineScript.ScriptWorldId.ApplicationWorld)
        script.setRunsOnSubFrames(False)
        script.setSourceCode(
            GOOGLE_LIGHT_JS if self.config.get("googleLight", True)
            else GOOGLE_BLACK_JS)
        return script

    def open_settings(self):
        """Open settings in the current tab (or an existing Settings tab),
        never spawning a pile of new tabs."""
        target = SETTINGS_PAGE.toString()
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if (not self._is_header(w) and hasattr(w, "url")
                    and w.url().toString().split("?")[0]
                    == SETTINGS_PAGE.toString().split("?")[0]):
                self.tabs.setCurrentIndex(i)
                return
        cur = self.current()
        if cur is not None and not self._is_header(cur):
            cur.load(QUrl(target))
        else:
            self.new_tab(url=target)

    def apply_font_size(self):
        px = int(self.config.get("minFont", 0) or 0)
        for profile in [self.profile] + list(self.session_profiles.values()):
            profile.settings().setFontSize(
                QWebEngineSettings.FontSize.MinimumFontSize, px)

    # ---- inspector (Chromium DevTools over remote debugging) ----
    def toggle_inspector(self):
        view = self.current()
        if view is None or not hasattr(view, "page"):
            return
        existing = getattr(view, "_devtools", None)
        if existing is not None:
            existing.close()
            view._devtools = None
            return
        # the embedded devtools:// frontend fails to load on some Qt
        # builds; the remote-debugging server serves the same DevTools
        # over http, which works everywhere
        cur = view.url().toString()
        reply = self._nam.get(QNetworkRequest(
            QUrl("http://127.0.0.1:9222/json/list")))
        reply.finished.connect(
            lambda r=reply, v=view, u=cur: self._open_inspector(r, v, u))

    def _open_inspector(self, reply, view, cur_url):
        base = "http://127.0.0.1:9222"
        frontend = base + "/"  # fallback: pick-a-page list
        try:
            targets = json.loads(bytes(reply.readAll()).decode())
            match = next((t for t in targets if t.get("type") == "page"
                          and t.get("url") == cur_url), None)
            match = match or next((t for t in targets
                                   if t.get("type") == "page"), None)
            if match and match.get("devtoolsFrontendUrl"):
                fe = match["devtoolsFrontendUrl"]
                frontend = fe if fe.startswith("http") else base + fe
        except Exception:
            pass
        reply.deleteLater()
        dt = QWebEngineView()
        dt.setWindowTitle("Inspector")
        dt.resize(1000, 640)
        dt.setWindowIcon(self.windowIcon())
        dt.load(QUrl(frontend))
        dt.destroyed.connect(lambda: setattr(view, "_devtools", None))
        dt.show()
        view._devtools = dt

    # ---- proxy switcher (SwitchyOmega-style) ----
    def _migrate_proxy(self):
        _migrate_proxy_config(self.config)

    def _apply_proxy_profile(self, name):
        """QtNetwork side (search suggestions, inspector fetch). Never
        app-wide: an application proxy would override the launch flags
        inside the web engine and freeze there, so it lives on the
        QNAM alone."""
        prof = next((p for p in self.config.get("proxyProfiles", [])
                     if p.get("name") == name), None)
        if prof is None:  # "system", "direct" or a deleted profile
            kind = (QNetworkProxy.ProxyType.NoProxy if name == "direct"
                    else QNetworkProxy.ProxyType.DefaultProxy)
            self._nam.setProxy(QNetworkProxy(kind))
            return
        kind = (QNetworkProxy.ProxyType.Socks5Proxy
                if prof.get("type") == "socks5"
                else QNetworkProxy.ProxyType.HttpProxy)
        proxy = QNetworkProxy(kind, prof.get("host", ""),
                              int(prof.get("port") or 0))
        if prof.get("user"):
            proxy.setUser(prof["user"])
            proxy.setPassword(prof.get("password", ""))
        self._nam.setProxy(proxy)

    def apply_proxy(self):
        self._migrate_proxy()
        active = self.config.get("activeProxy", "system")
        if active == "auto":
            # Chromium routes per-site via the PAC baked in at launch;
            # the QNAM can only take one proxy, so it follows the
            # rules' default profile
            auto = self.config.get("proxyAuto") or {}
            self._apply_proxy_profile(auto.get("default", "direct"))
        else:
            self._apply_proxy_profile(active)
        if self._proxy_restart_needed():
            self._show_restart_toast("Proxy change applies after a restart")
        self._update_proxy_btn()

    def _proxy_restart_needed(self):
        """The web engine reads its proxy flags only at startup:
        true when the config drifted from what this process was
        launched with."""
        return (_PROXY_FLAGS_AT_LAUNCH is not None
                and _proxy_launch_flags(self.config)
                != _PROXY_FLAGS_AT_LAUNCH)

    def _proxy_auth(self, url, authenticator, proxy_host):
        # Chromium asks for proxy credentials itself; answer from the
        # matching profile (QNetworkProxy user/password never reach it)
        host = proxy_host.rsplit(":", 1)[0]
        for p in self.config.get("proxyProfiles", []):
            if p.get("user") and p.get("host") in (proxy_host, host):
                authenticator.setUser(p["user"])
                authenticator.setPassword(p.get("password", ""))
                return

    def _show_restart_toast(self, message):
        """Update-toast styling, but for settings Chromium only reads
        at launch; stays until dismissed or acted on."""
        if self._toast:
            return
        toast = QWidget(self, objectName="toast")
        toast.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QHBoxLayout(toast)
        lay.setContentsMargins(14, 8, 8, 8)
        lay.setSpacing(10)
        self._toast_label = QLabel(message)
        restart = QToolButton(text="Restart now")
        close = QToolButton(text="\u2715", objectName="tabclose")
        lay.addWidget(self._toast_label)
        lay.addWidget(restart)
        lay.addWidget(close)

        self._toast = toast
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._hide_toast)
        close.clicked.connect(self._hide_toast)
        restart.clicked.connect(self.restart)

        self._place_toast()
        toast.show()
        toast.raise_()

    def _proxy_profiles(self):
        base = [{"name": "system", "label": "System", "builtin": True},
                {"name": "direct", "label": "Direct", "builtin": True}]
        return base + [dict(p, label=p["name"], builtin=False)
                       for p in self.config.get("proxyProfiles", [])]

    def _proxy_menu(self):
        menu = QMenu(self)
        active = self.config.get("activeProxy", "system")
        auto_mark = "\u2713 " if active == "auto" else "    "
        menu.addAction(auto_mark + "Auto (by site rules)").triggered.connect(
            lambda: self.set_active_proxy("auto"))
        menu.addSeparator()
        for p in self._proxy_profiles():
            mark = "\u2713 " if p["name"] == active else "    "
            menu.addAction(mark + p["label"]).triggered.connect(
                lambda _, n=p["name"]: self.set_active_proxy(n))
        menu.addSeparator()
        menu.addAction("Manage profiles\u2026").triggered.connect(
            self.open_settings)
        b = self._proxy_btn
        menu.exec(b.mapToGlobal(b.rect().bottomLeft()))

    def set_active_proxy(self, name):
        self.config["activeProxy"] = name
        self.save_config()
        self.apply_proxy()

    def _update_proxy_btn(self):
        btn = getattr(self, "_proxy_btn", None)
        if btn is None:
            return
        active = self.config.get("activeProxy", "system")
        label = {"system": "System", "direct": "Direct",
                 "auto": "Auto"}.get(active, active)
        btn.setToolTip("Proxy: " + label)
        # a filled dot when a proxy is actually routing traffic
        btn.setText("📡" if active not in ("system", "direct")
                    else "📡")
        btn.setStyleSheet(
            "QToolButton { color: %s; }" %
            ("#a6e3a1" if active not in ("system", "direct") else "#cdd6f4"))

    def apply_language(self):
        """The chosen language reaches websites (Accept-Language, so
        Google speaks it too) and the browser's own pages."""
        lang = self.config.get("translateLang", "de")
        accept = lang if lang.startswith("en") else lang + ",en"
        for profile in [self.profile] + list(self.session_profiles.values()):
            profile.setHttpAcceptLanguage(accept)
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if hasattr(w, "url") and w.url().scheme() == "file":
                w.reload()

    def refresh_google_scripts(self):
        """Swap the Google white/black script in every cookie jar."""
        for profile in [self.profile] + list(self.session_profiles.values()):
            scripts = profile.scripts()
            for old in scripts.find("google-mode"):
                scripts.remove(old)
            scripts.insert(self._google_script())

    @staticmethod
    def _plugin_glob_to_regex(seg):
        """Glob segment -> regex source: * -> .*, rest escaped
        ( / escaped too, for the JS /.../ literal)."""
        out = []
        for ch in seg:
            if ch == "*":
                out.append(".*")
            elif ch == "/":
                out.append(r"\/")
            else:
                out.append(re.escape(ch))
        return "".join(out)

    def _plugin_pattern_to_regex(self, pattern):
        """Chrome-style match pattern -> regex on the FULL url, matched
        by component so `*.x.com` covers x.com and its subdomains and a
        stray `.x.com/` in a path can't trigger it."""
        m = re.match(r"^(\*|https?|file|ftp)://([^/]*)(/.*)?$", pattern)
        if not m:  # not a scheme://host/path pattern: fall back to a glob
            return "^%s$" % self._plugin_glob_to_regex(pattern)
        scheme, host, path = m.group(1), m.group(2), m.group(3) or "/*"
        scheme_re = r"https?" if scheme == "*" else re.escape(scheme)
        if host == "*":
            host_re = r"[^/]+"
        elif host.startswith("*."):
            host_re = r"(?:[^/]+\.)?" + re.escape(host[2:])
        else:
            host_re = self._plugin_glob_to_regex(host)
        path_re = self._plugin_glob_to_regex(path)
        return r"^%s:\/\/%s%s$" % (scheme_re, host_re, path_re)

    def _plugin_wrap(self, source):
        """Honor // @match and // @include lines: the script only runs
        on matching URLs (any pattern may match). None = everywhere."""
        patterns = re.findall(r"^\s*//\s*@(?:match|include)\s+(\S+)",
                              source, re.MULTILINE)
        if not patterns:
            return source
        regex = "|".join(self._plugin_pattern_to_regex(p) for p in patterns)
        return "if (new RegExp(%s).test(location.href)) {\n%s\n}" % (
            json.dumps(regex), source)

    def _load_plugins(self):
        """Every *.user.js in the plugins folder becomes an injectable
        script; the folder is created on first start."""
        try:
            self.plugins_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return []
        scripts = []
        for f in sorted(self.plugins_dir.glob("*.user.js")):
            try:
                source = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            script = QWebEngineScript()
            # source first: setSourceCode parses ==UserScript== metadata
            # and would overwrite the name / injection point set before
            script.setSourceCode(self._plugin_wrap(source))
            script.setName("plugin-" + f.name)
            script.setInjectionPoint(
                QWebEngineScript.InjectionPoint.DocumentReady)
            script.setWorldId(QWebEngineScript.ScriptWorldId.ApplicationWorld)
            script.setRunsOnSubFrames(False)
            scripts.append(script)
        return scripts

    def _plugin_toast(self, name):
        self.bridge.updateFinished.emit("Plugin installed: " + name)
        self._show_toast()
        if self._toast:
            self._toast_label.setText("Plugin installed ✓")

    def _plugin_downloaded(self, request):
        if request.isFinished() and request.state() == \
                request.DownloadState.DownloadCompleted:
            self.reload_plugins()
            self._plugin_toast(request.downloadFileName())

    def _safe_plugin_name(self, filename):
        base = re.sub(r"[^\w.-]", "_", Path(filename).name)
        if not base.endswith(".user.js"):
            base = base.removesuffix(".js") + ".user.js"
        return base

    def save_plugin(self, filename, source):
        """Write a userscript into the plugins folder and activate it."""
        try:
            self.plugins_dir.mkdir(parents=True, exist_ok=True)
            (self.plugins_dir / self._safe_plugin_name(filename)).write_text(
                source, encoding="utf-8")
        except OSError:
            return False
        self.reload_plugins()
        self._plugin_toast(self._safe_plugin_name(filename))
        return True

    def install_starter(self, plugin_id):
        entry = STARTER_PLUGINS.get(plugin_id)
        if entry is None:
            return False
        return self.save_plugin(plugin_id + ".user.js", entry[2])

    def add_plugin_from_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Add plugin", str(Path.home()),
            "Userscripts (*.user.js *.js)")
        if not path:
            return
        try:
            source = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        self.save_plugin(Path(path).name, source)

    def reload_plugins(self):
        """Re-read the plugins folder into every cookie jar."""
        old_names = self.plugin_script_names
        self.plugin_scripts = self._load_plugins()
        self.plugin_script_names = [s.name() for s in self.plugin_scripts]
        for profile in [self.profile] + list(self.session_profiles.values()):
            scripts = profile.scripts()
            for name in old_names:
                for stale in scripts.find(name):
                    scripts.remove(stale)
            for script in self.plugin_scripts:
                scripts.insert(script)

    def _profile_for(self, group, session="main"):
        """Cookies are per virtual browser: every tab in it — grouped
        or not — shares that browser's jar."""
        return self._session_profile(session or "main")

    def _session_profile(self, sid):
        if sid == "main":
            return self.profile
        if sid not in self.session_profiles:
            self.session_profiles[sid] = self._make_profile("browser-s-" + sid)
        return self.session_profiles[sid]

    def _sync_profile(self, view):
        """Keep a tab in its virtual browser's cookie jar (no-op unless
        it somehow ended up in the wrong one)."""
        want = self._profile_for(self._group_of(view),
                                 getattr(view, "session", "main"))
        if view.page().profile() is want:
            return
        url = view.url()
        target = url if url.toString() else QUrl(getattr(view, "_requested", ""))
        view.attach_profile(want)
        view.load(target if target.toString() else START_PAGE)

    def _download(self, request):
        # a .user.js is a plugin: install it straight into the folder
        name = request.downloadFileName()
        if name.endswith(".user.js"):
            request.setDownloadDirectory(str(self.plugins_dir))
            request.setDownloadFileName(name)
            request.accept()
            request.isFinishedChanged.connect(
                lambda r=request: self._plugin_downloaded(r))
            return
        if self.config.get("askDownload"):
            path, _ = QFileDialog.getSaveFileName(
                self, "Save file",
                str(DOWNLOAD_DIR / request.downloadFileName()))
            if not path:
                request.cancel()
                return
            request.setDownloadDirectory(str(Path(path).parent))
            request.setDownloadFileName(Path(path).name)
            request.accept()
            widget = DownloadWidget(request, self._dismiss_download)
            self.dllay.insertWidget(self.dllay.count() - 1, widget)
            self.dlbar.show()
            return
        request.setDownloadDirectory(str(DOWNLOAD_DIR))
        # don't overwrite existing files: name.pdf -> name (1).pdf
        name = request.downloadFileName()
        stem, suffix = Path(name).stem, Path(name).suffix
        n = 1
        while (DOWNLOAD_DIR / name).exists():
            name = f"{stem} ({n}){suffix}"
            n += 1
        request.setDownloadFileName(name)
        request.accept()
        widget = DownloadWidget(request, self._dismiss_download)
        self.dllay.insertWidget(self.dllay.count() - 1, widget)
        self.dlbar.show()

    def restart(self):
        """Relaunch the browser (used after an update)."""
        if getattr(self, "_instance_server", None) is not None:
            # free the single-instance socket so the successor
            # becomes the new primary instead of handing off to us
            self._instance_server.close()
            QLocalServer.removeServer(SINGLE_INSTANCE_SOCKET)
        # successor waits for this process to exit before starting
        os.environ["BROWSER_RESTART_WAIT"] = str(os.getpid())
        QProcess.startDetached(sys.executable, [str(APP_DIR / "browser.py")])
        QApplication.instance().quit()

    def closeEvent(self, event):
        # closing the window from the compositor (e.g. Super+Q) must end
        # the process too — a lingering ghost would hold the
        # single-instance socket and swallow future launches
        QApplication.instance().quit()
        super().closeEvent(event)

    def _dismiss_download(self, widget):
        self.dllay.removeWidget(widget)
        widget.deleteLater()
        if self.dllay.count() <= 1:  # only the stretch left
            self.dlbar.hide()


_PROXY_FLAGS_AT_LAUNCH = None  # what Chromium was started with


def _migrate_proxy_config(config):
    # old single-proxy config -> a named profile + active selection
    if "activeProxy" in config:
        return config
    old = config.get("proxy")
    if isinstance(old, dict) and old.get("mode") == "custom":
        config["proxyProfiles"] = [
            {"name": "Proxy", "type": old.get("type", "http"),
             "host": old.get("host", ""), "port": old.get("port", 0)}]
        config["activeProxy"] = "Proxy"
    else:
        config["activeProxy"] = (old or {}).get("mode", "system")
    return config


def _proxy_hostport(prof):
    """Sanitized (host, port) of a profile, or None if unusable."""
    if not prof:
        return None
    host = re.sub(r"[^A-Za-z0-9.-]", "", str(prof.get("host", "")))
    try:
        port = int(prof.get("port") or 0)
    except (TypeError, ValueError):
        port = 0
    return (host, port) if host and port else None


def _proxy_launch_flags(config):
    """Chromium flags for the configured proxy. The web engine reads
    proxy settings only once, at startup: a Qt application proxy set
    later is ignored, and one set earlier overrides these flags and
    then freezes. So the flags are the single source of truth and any
    change means a restart. Per-site rules become a PAC script — the
    only per-host routing Chromium offers."""
    active = config.get("activeProxy", "system")
    profiles = {p.get("name"): p for p in config.get("proxyProfiles", [])}
    if active == "direct":
        return "--no-proxy-server"
    if active != "auto":
        hp = _proxy_hostport(profiles.get(active))
        if hp is None:  # "system" or a broken/deleted profile
            return ""
        scheme = ("socks5://" if profiles[active].get("type") == "socks5"
                  else "")
        return "--proxy-server=%s%s:%d" % (scheme, hp[0], hp[1])
    auto = config.get("proxyAuto") or {}

    def directive(name):
        # a single PROXY entry, no "; DIRECT" tail: a dead proxy must
        # block the site, not silently leak traffic directly
        hp = _proxy_hostport(profiles.get(name))
        if hp is None:  # "direct", "system" or a deleted profile
            return "DIRECT"
        kind = ("SOCKS5" if profiles[name].get("type") == "socks5"
                else "PROXY")
        return "%s %s:%d" % (kind, hp[0], hp[1])

    def condition(pattern):
        # mirrors the old _host_matches semantics in PAC-JavaScript
        pat = re.sub(r"[^a-z0-9.*-]", "", (pattern or "").strip().lower())
        if not pat:
            return None
        if pat.startswith("*."):
            pat = pat[2:]
        if "*" in pat:
            return 'shExpMatch(host, "%s")' % pat
        return 'host == "%s" || dnsDomainIs(host, ".%s")' % (pat, pat)

    lines = ["function FindProxyForURL(url, host) {",
             "  host = host.toLowerCase();"]
    for rule in auto.get("rules", []):
        cond = condition(rule.get("pattern", ""))
        if cond is None:
            continue
        lines.append('  if (%s) return "%s";'
                     % (cond, directive(rule.get("profile", "direct"))))
    lines.append('  return "%s";' % directive(auto.get("default", "direct")))
    lines.append("}")
    pac = base64.b64encode("\n".join(lines).encode()).decode()
    return ("--proxy-pac-url=data:application/x-ns-proxy-autoconfig;base64,"
            + pac)


def _install_proxy_flags():
    """Bake the proxy rules into Chromium's command line; must run
    before the QApplication (and thus the web engine) exists. Any
    proxy flags already in the environment are stripped first: an
    in-app restart hands the child the parent's flags, and a stale
    --no-proxy-server/--proxy-server/--proxy-pac-url would silently
    win over the current config."""
    global _PROXY_FLAGS_AT_LAUNCH
    try:
        config = json.loads(CONFIG_FILE.read_text())
    except (OSError, ValueError):
        config = {}
    flags = _proxy_launch_flags(_migrate_proxy_config(config))
    env = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    env = re.sub(r"\s*--(?:proxy-server|proxy-pac-url)=\S+", "", env)
    env = re.sub(r"\s*--no-proxy-server\b", "", env)
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
        env + " " + flags if flags else env)
    _PROXY_FLAGS_AT_LAUNCH = flags
    return flags


SINGLE_INSTANCE_SOCKET = "browser-single-instance"


def _pid_alive(pid):
    if sys.platform == "win32":
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def main():
    # a URL argument means we were asked to open a link (e.g. as the
    # system default browser)
    url = sys.argv[1] if len(sys.argv) > 1 else None

    # started by our own restart(): let the old process finish dying
    # so the profile and socket are free
    predecessor = os.environ.pop("BROWSER_RESTART_WAIT", None)
    if predecessor:
        for _ in range(60):
            try:
                if not _pid_alive(int(predecessor)):
                    break
            except ValueError:
                break
            time.sleep(0.1)

    # single instance: two instances sharing one profile breaks Chromium's
    # network/cache storage, so hand the link to the running one instead
    probe = QLocalSocket()
    probe.connectToServer(SINGLE_INSTANCE_SOCKET)
    if probe.waitForConnected(300):
        probe.write((url or "raise").encode())
        probe.flush()
        probe.waitForBytesWritten(300)
        return

    QGuiApplication.setDesktopFileName("browser")
    _install_proxy_flags()
    app = QApplication(sys.argv)
    app.setApplicationName("browser")
    app.setWindowIcon(QIcon(str(APP_DIR / "icon.svg")))
    app.setStyleSheet(STYLE)
    win = Browser(initial_url=url)

    QLocalServer.removeServer(SINGLE_INSTANCE_SOCKET)
    server = QLocalServer()
    server.listen(SINGLE_INSTANCE_SOCKET)
    win._instance_server = server

    def handoff():
        conn = server.nextPendingConnection()

        def read():
            message = bytes(conn.readAll()).decode().strip()
            win.new_tab(url=None if message in ("", "raise") else message)
            win.showNormal()
            win.raise_()
            win.activateWindow()
        conn.readyRead.connect(read)

    server.newConnection.connect(handoff)

    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
