"""Capture de sites web au format WebUI, pour un test hors domaine pré-annoté par le code.

    python -m sbc_vision.perception.datasets.capture_web \
        --sites data/manifests/ood-sites.json --pages-per-site 10 --out <captures>/ood

Pour chaque site : la page d'accueil telle qu'un visiteur la découvre (bandeau de cookies
compris), puis, bandeau refermé, des pages de rubriques différentes tirées parmi les liens de
l'accueil (graine fixe). Chaque page est enregistrée dans son dossier avec les fichiers de
WebUI : capture, arbre d'accessibilité (`Accessibility.getFullAXTree`), boîtes et styles
calculés des nœuds (`DOMSnapshot.captureSnapshot`), URL. `build_webui` en tire ensuite les
étiquettes, exactement comme pour WebUI ; elles restent à vérifier à la main.
"""

import argparse
import asyncio
import gzip
import io
import json
import random
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urldefrag, urlsplit

from PIL import Image
from playwright.async_api import TimeoutError as PageTimeout
from playwright.async_api import async_playwright

from sbc_vision.perception.datasets.webui import DESKTOP_DEVICES

STYLES = ("display", "visibility", "opacity")
CONSENT = re.compile(
    r"^\s*(tout accepter|accepter( et fermer| tout)?|j'accepte|accept all)\s*$", re.I
)
SETTLE_MS = 3000


def _viewport(device: str) -> dict:
    width, height = device.removeprefix("default_").split("-")
    return {"width": int(width), "height": int(height)}


def _write_json(path: Path, value) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump(value, handle)


async def _snapshot(page, folder: Path, device: str) -> dict:
    """Capture et code de la page, au même instant autant que possible."""
    png = await page.screenshot()
    cdp = await page.context.new_cdp_session(page)
    axtree = await cdp.send("Accessibility.getFullAXTree")
    snapshot = await cdp.send("DOMSnapshot.captureSnapshot", {"computedStyles": list(STYLES)})
    width, height = await page.evaluate("[innerWidth, innerHeight]")
    await cdp.detach()

    strings = snapshot["strings"]
    document = snapshot["documents"][0]
    backend_ids = document["nodes"]["backendNodeId"]
    layout = document["layout"]
    boxes: dict[str, dict] = {}
    styles: dict[str, dict] = {}
    for node_index, bounds, style in zip(
        layout["nodeIndex"], layout["bounds"], layout["styles"], strict=True
    ):
        key = str(backend_ids[node_index])
        x, y, w, h = bounds
        if key in boxes:  # plusieurs boîtes de mise en page (texte sur deux lignes) : leur union
            old = boxes[key]
            x1, y1 = min(old["x"], x), min(old["y"], y)
            x2 = max(old["x"] + old["width"], x + w)
            y2 = max(old["y"] + old["height"], y + h)
            x, y, w, h = x1, y1, x2 - x1, y2 - y1
        boxes[key] = {"x": x, "y": y, "width": w, "height": h}
        if style:  # les nœuds de texte n'ont pas de style calculé propre
            styles[key] = {name: strings[i] for name, i in zip(STYLES, style, strict=True)}
    # La zone d'affichage : la racine du document a la taille de la fenêtre, comme dans WebUI.
    root = next(n for n in axtree["nodes"] if n.get("role", {}).get("value") == "RootWebArea")
    boxes[str(root["backendDOMNodeId"])] = {"x": 0, "y": 0, "width": width, "height": height}

    folder.mkdir(parents=True, exist_ok=True)
    Image.open(io.BytesIO(png)).save(
        folder / f"{device}-screenshot.webp", lossless=True, quality=100
    )
    _write_json(folder / f"{device}-axtree.json.gz", axtree)
    _write_json(folder / f"{device}-bb.json.gz", boxes)
    _write_json(folder / f"{device}-style.json.gz", styles)
    (folder / f"{device}-url.txt").write_text(page.url, encoding="utf-8")
    return {"url": page.url, "title": await page.title(), "device": device}


async def _dismiss_consent(page) -> bool:
    """Accepte le bandeau de cookies. Le bouton est cherché par son texte, pas par son rôle :
    certains sites le déclarent mal (un `<button role="listitem">`)."""
    for frame in page.frames:
        buttons = frame.locator("button, [role=button], a").filter(has_text=CONSENT)
        if await buttons.count():
            await buttons.first.click(timeout=5000)
            await page.wait_for_timeout(1000)
            return True
    return False


def _section_links(links: list[str], host: str, count: int, seed: int) -> list[str]:
    """Liens du même site, une page par rubrique (premier segment du chemin) tant que possible."""
    by_section: dict[str, list[str]] = {}
    for link in links:
        url, _ = urldefrag(link)
        parts = urlsplit(url)
        if parts.hostname != host or parts.path in ("", "/"):
            continue
        section = parts.path.strip("/").split("/")[0]
        by_section.setdefault(section, [])
        if url not in by_section[section]:
            by_section[section].append(url)
    rng = random.Random(seed)
    sections = sorted(by_section)
    rng.shuffle(sections)
    picked: list[str] = []
    while len(picked) < count and any(by_section[s] for s in sections):
        for section in sections:
            if by_section[section] and len(picked) < count:
                candidates = sorted(by_section[section])
                url = rng.choice(candidates)
                by_section[section].remove(url)
                picked.append(url)
    return picked


async def capture_site(browser, site: dict, pages: int, seed: int, out: Path):
    """Pages capturées et pages écartées. Un refus du site (code HTTP d'erreur) arrête sa
    capture : on ne contourne pas un refus d'accès."""
    context = await browser.new_context(locale="fr-FR", device_scale_factor=1)
    page = await context.new_page()
    records, skipped = [], []
    device = DESKTOP_DEVICES[0]
    await page.set_viewport_size(_viewport(device))
    response = await page.goto(site["start_url"], wait_until="load", timeout=60000)
    if response is None or response.status >= 400:
        raise RuntimeError(f"{site['name']} refuse l'accueil ({response and response.status})")
    await page.wait_for_timeout(SETTLE_MS)
    records.append(await _snapshot(page, out / f"{site['name']}-00", device))
    consent = await _dismiss_consent(page)
    host = urlsplit(page.url).hostname
    links = await page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
    for index, url in enumerate(_section_links(links, host, pages - 1, seed), start=1):
        device = DESKTOP_DEVICES[index % len(DESKTOP_DEVICES)]
        await page.set_viewport_size(_viewport(device))
        try:
            response = await page.goto(url, wait_until="load", timeout=60000)
        except PageTimeout:
            skipped.append({"site": site["name"], "url": url, "reason": "délai dépassé"})
            continue
        if response is None or response.status >= 400:
            status = response and response.status
            skipped.append({"site": site["name"], "url": url, "reason": f"refus ({status})"})
            break
        await page.wait_for_timeout(SETTLE_MS)
        if urlsplit(page.url).hostname != host:
            skipped.append({"site": site["name"], "url": url, "reason": "redirigé hors du site"})
            continue
        records.append(await _snapshot(page, out / f"{site['name']}-{index:02d}", device))
    await context.close()
    for record in records:
        record.update(site=site["name"], category=site["category"], consent_dismissed=consent)
    return records, skipped


async def capture(sites: list[dict], pages: int, seed: int, out: Path):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        records, skipped = [], []
        for site in sites:
            site_records, site_skipped = await capture_site(browser, site, pages, seed, out)
            records.extend(site_records)
            skipped.extend(site_skipped)
        await browser.close()
    return records, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sites", type=Path, required=True)
    parser.add_argument(
        "--only", nargs="+", help="ne recapturer que ces sites (les autres restent)"
    )
    parser.add_argument("--pages-per-site", type=int, default=10)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    sites = json.loads(args.sites.read_text(encoding="utf-8"))
    if args.only:
        sites = [site for site in sites if site["name"] in args.only]
    names = {site["name"] for site in sites}
    log_path = args.out / "capture.json"
    log = json.loads(log_path.read_text()) if log_path.exists() else {"pages": [], "skipped": []}
    log = {
        key: [row for row in log[key] if row["site"] not in names] for key in ("pages", "skipped")
    }
    for site in sites:  # une recapture remplace toutes les pages du site
        for folder in args.out.glob(f"{site['name']}-[0-9][0-9]"):
            shutil.rmtree(folder)
    records, skipped = asyncio.run(capture(sites, args.pages_per_site, args.seed, args.out))
    captured_at = datetime.now(UTC).isoformat(timespec="seconds")
    for record in records:
        record["captured_at"] = captured_at
    log["pages"] += records
    log["skipped"] += skipped
    log_path.write_text(json.dumps(log, indent=2, ensure_ascii=False))
    print(json.dumps({"pages": len(records), "skipped": skipped}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
