"""Contrôles autonomes du kit de références, sans navigateur ni accès réseau."""

import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent
errors = []
links = 0


def check_link(source, value):
    global links
    value = value.strip()
    if not value or value.startswith(("data:", "#")):
        return
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc:
        errors.append(f"{source.name}: dépendance externe {value[:120]}")
        return
    target = (source.parent / unquote(parsed.path)).resolve()
    if not target.is_relative_to(ROOT) or not target.is_file():
        errors.append(f"{source.name}: lien absent ou hors dossier {value}")
    links += 1


def check_css(source, value):
    for url in re.findall(r"url\(\s*[\"']?([^\)\"']+)", value):
        check_link(source, url)
    if re.search(r"@import\s", value):
        errors.append(f"{source.name}: import CSS non autonome")


class Page(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.source = source
        self.csp = False

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag in {"iframe", "object", "embed", "base"}:
            errors.append(f"{self.source.name}: balise exclue {tag}")
        if any(key.lower().startswith("on") for key in attrs):
            errors.append(f"{self.source.name}: gestionnaire JS en ligne")
        if tag == "script" and attrs.get("src") != "../viewer.js":
            errors.append(f"{self.source.name}: script inattendu")
        if tag == "meta" and attrs.get("http-equiv", "").lower() == "content-security-policy":
            self.csp = "connect-src 'none'" in attrs.get("content", "")
        for key in ("src", "href", "xlink:href", "poster", "data-sim-canvas"):
            if attrs.get(key):
                check_link(self.source, attrs[key])
        if attrs.get("style"):
            check_css(self.source, attrs["style"])


def main():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    for page in manifest["pages"]:
        source = ROOT / page["html"]
        text = source.read_text()
        parser = Page(source)
        parser.feed(text)
        if not parser.csp:
            errors.append(f"{source.name}: CSP manquante")
        if re.search(r"(?:is-active|ut-list-active-tag-view)", text):
            errors.append(f"{source.name}: appartenance réelle à l'équipe conservée")
        if re.search(r"83,127|Local FC|Est\. Sep 2025", text):
            errors.append(f"{source.name}: ancienne donnée de compte conservée")
        metadata = ROOT / page["metadata"]
        if not metadata.is_file():
            errors.append(f"Métadonnées absentes : {metadata.name}")
    for source in ROOT.rglob("*.css"):
        check_css(source, source.read_text())
    for entry in manifest["assets"].values():
        if entry.get("file") and not (ROOT / entry["file"]).is_file():
            errors.append(f"Ressource absente : {entry['file']}")
    if manifest["missing_assets"]:
        errors.append("Des ressources publiques sont absentes ; voir manifest.json")
    if errors:
        for error in errors:
            print(error)
        raise SystemExit(1)
    print(f"OK : {len(manifest['pages'])} écrans, {links} références locales vérifiées.")
    print("Aucun script EA, accès externe HTML/CSS ou marqueur réel d'équipe conservé.")


if __name__ == "__main__":
    main()
