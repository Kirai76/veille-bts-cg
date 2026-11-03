#!/usr/bin/env python3
"""Collecte les actualités, puis construit le site statique dans _site/.

Utilise uniquement la bibliothèque standard de Python.
Lancé toutes les heures par .github/workflows/update.yml.
"""
import html
import json
import os
import re
import shutil
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "_site"
NEWS_FILE = ROOT / "data" / "news.json"
JOURNAL_FILE = ROOT / "data" / "journal.json"
TEMPLATE = ROOT / "template.html"

# Adresse publique du site. Change-la si tu renommes le dépôt.
SITE_URL = "https://kirai76.github.io/veille-bts-cg/"

THEMES = {
    "fact": "Facturation",
    "fisc": "Fiscalité",
    "soc": "Social",
    "compta": "Comptabilité",
    "alt": "Alternance",
}

# (thème, recherche). Modifie cette liste pour suivre d'autres sujets.
QUERIES = [
    ("fact", "facturation électronique"),
    ("fact", "e-reporting facture plateforme agréée"),
    ("fisc", "loi de finances 2027 entreprises"),
    ("fisc", "TVA entreprises réforme"),
    ("fisc", "impôt sur les sociétés"),
    ("soc", "paie cotisations sociales Urssaf"),
    ("soc", "DSN employeurs paie"),
    ("compta", "plan comptable général ANC"),
    ("compta", "expert-comptable profession comptable"),
    ("alt", "aide embauche apprenti"),
    ("alt", "BTS comptabilité gestion"),
    ("alt", "apprentissage alternance réforme"),
]

WHEN = "30d"          # fenêtre de recherche demandée à Google Actualités
KEEP_DAYS = 60        # on garde les articles pendant 60 jours
MAX_STORED = 150
MAX_SHOWN = 60
UA = "Mozilla/5.0 (compatible; veille-bts-cg/1.0)"

MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
MOIS_LONG = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
             "septembre", "octobre", "novembre", "décembre"]


def feed_url(query):
    q = urllib.parse.quote_plus(f"{query} when:{WHEN}")
    return f"https://news.google.com/rss/search?q={q}&hl=fr&gl=FR&ceid=FR:fr"


def fetch(url):
    test = os.environ.get("VEILLE_TEST_FEED")  # pour les tests : lit un fichier local
    if test:
        return Path(test).read_bytes()
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (attempt + 1))
    raise last


def parse(data, theme):
    root = ET.fromstring(data)
    items = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        pub = it.findtext("pubDate")
        src_el = it.find("source")
        source = (src_el.text or "").strip() if src_el is not None and src_el.text else ""
        if source and title.endswith(" - " + source):
            title = title[: -len(source) - 3].strip()
        elif not source and " - " in title:
            title, source = [p.strip() for p in title.rsplit(" - ", 1)]
        if not title or not link.startswith(("http://", "https://")) or not pub:
            continue
        try:
            dt = parsedate_to_datetime(pub)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt = dt.astimezone(timezone.utc)
        except (TypeError, ValueError):
            continue
        items.append({
            "title": title,
            "link": link,
            "source": source or "Source non indiquée",
            "ts": int(dt.timestamp()),
            "theme": theme,
        })
    return items


def norm(title):
    return re.sub(r"[^a-z0-9]+", "", title.lower().replace("é", "e").replace("è", "e").replace("à", "a"))


def load_previous():
    try:
        return json.loads(NEWS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"items": [], "last_success": None}


def collect():
    prev = load_previous()
    now = datetime.now(timezone.utc)
    new_items, status = [], []
    for theme, query in QUERIES:
        try:
            items = parse(fetch(feed_url(query)), theme)
            status.append({"query": query, "ok": True, "count": len(items)})
            new_items.extend(items)
        except Exception as e:  # noqa: BLE001
            status.append({"query": query, "ok": False, "error": str(e)[:120]})
            print(f"[avertissement] flux en échec ({query}) : {e}", file=sys.stderr)
    ok = sum(1 for s in status if s["ok"])
    print(f"{ok}/{len(status)} flux ont répondu, {len(new_items)} articles lus.")

    limit = int((now - timedelta(days=KEEP_DAYS)).timestamp())
    seen, merged = set(), []
    for it in sorted(new_items + prev.get("items", []), key=lambda x: -x["ts"]):
        k = norm(it["title"])
        if not k or k in seen or it["ts"] < limit or it["ts"] > int(now.timestamp()) + 86400:
            continue
        seen.add(k)
        merged.append(it)
    merged = merged[:MAX_STORED]

    data = {
        "updated": now.isoformat(timespec="seconds"),
        "last_success": now.isoformat(timespec="seconds") if ok else prev.get("last_success"),
        "feeds": status,
        "items": merged,
    }
    NEWS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


def esc(s):
    return html.escape(s, quote=True)


def fr_date(dt):
    return f"{dt.day} {MOIS[dt.month - 1]} {dt.year}"


def render_news(data):
    items = data["items"][:MAX_SHOWN]
    if not items:
        return '<div class="empty">Aucune actualité récente n\'a pu être récupérée. Le prochain essai a lieu dans l\'heure.</div>'
    out = []
    for it in items:
        d = datetime.fromtimestamp(it["ts"], timezone.utc)
        out.append(
            f'<article class="entry news" data-t="{esc(it["theme"])}">'
            f'<div class="e-date"><b>{fr_date(d)}</b></div>'
            f'<div class="e-body"><div class="theme">{esc(THEMES.get(it["theme"], ""))}</div>'
            f'<h3><a href="{esc(it["link"])}" target="_blank" rel="noopener noreferrer">{esc(it["title"])}</a></h3>'
            f'<div class="src">Source : {esc(it["source"])}</div></div></article>'
        )
    return "\n".join(out)


def render_journal(today):
    entries = json.loads(JOURNAL_FILE.read_text(encoding="utf-8"))
    out = []
    for e in sorted(entries, key=lambda x: x["d"], reverse=True):
        d = datetime.strptime(e["d"], "%Y-%m-%d").date()
        future = d > today
        pill = '<span class="pill next">À venir</span>' if future else '<span class="pill">Publié</span>'
        keep = ""
        if e.get("keep"):
            keep = f'<p class="retenir"><strong>À retenir</strong>{esc(e["keep"])}</p>'
        srcs = " ".join(
            f'<a href="{esc(u)}" target="_blank" rel="noopener noreferrer">{esc(n)}</a>' for n, u in e["src"]
        )
        out.append(
            f'<article class="entry" data-t="{esc(e["t"])}">'
            f'<div class="e-date"><b>{fr_date(d)}</b>{pill}</div>'
            f'<div class="e-body"><div class="theme">{esc(THEMES[e["t"]])}</div>'
            f'<h3>{esc(e["title"])}</h3><p>{esc(e["body"])}</p>{keep}'
            f'<div class="src">Sources : {srcs}</div></div></article>'
        )
    return "\n".join(out)


def build(data):
    try:
        from zoneinfo import ZoneInfo
        local = datetime.now(ZoneInfo("Europe/Paris"))
    except Exception:  # noqa: BLE001
        local = datetime.now(timezone.utc)
    today = local.date()
    updated_long = f"{local.day} {MOIS_LONG[local.month - 1]} {local.year}"
    updated_hour = local.strftime("%H h %M")

    ls = data.get("last_success")
    if ls:
        d = datetime.fromisoformat(ls).astimezone(local.tzinfo)
        collect_line = f"Dernière collecte réussie le {d.day} {MOIS_LONG[d.month - 1]} {d.year} à {d.strftime('%H h %M')} (heure de Paris)."
    else:
        collect_line = "Aucune collecte réussie pour le moment."
    ok = sum(1 for s in data["feeds"] if s["ok"])
    collect_line += f" {ok} recherches sur {len(data['feeds'])} ont répondu."

    page = TEMPLATE.read_text(encoding="utf-8")
    repl = {
        "<!--NEWS-->": render_news(data),
        "<!--JOURNAL-->": render_journal(today),
        "{{UPDATED_LONG}}": updated_long,
        "{{UPDATED_HOUR}}": updated_hour,
        "{{COLLECT_LINE}}": esc(collect_line),
        "{{SITE_URL}}": SITE_URL,
        "{{TODAY_ISO}}": today.isoformat(),
    }
    for k, v in repl.items():
        page = page.replace(k, v)

    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "data").mkdir(parents=True)
    (OUT / "index.html").write_text(page, encoding="utf-8")
    shutil.copy(NEWS_FILE, OUT / "data" / "news.json")
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}sitemap.xml\n", encoding="utf-8")
    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"  <url><loc>{SITE_URL}</loc><lastmod>{today.isoformat()}</lastmod><changefreq>hourly</changefreq></url>\n"
        "</urlset>\n",
        encoding="utf-8",
    )
    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    print(f"Site construit dans {OUT}")


if __name__ == "__main__":
    build(collect())
