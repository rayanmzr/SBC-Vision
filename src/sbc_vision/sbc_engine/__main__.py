"""Commande commune : python -m sbc_vision.sbc_engine --help."""

import argparse
import json
import os
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import httpx

from .catalogue import ATTRIBUTION, BASE_URL, Futbin, import_catalog, import_file, open_database
from .inventory import list_items, load_pool, save_item, seed_demo, set_protected
from .models import Challenge, ClubItem, OcrInput
from .solver import alternatives, greedy, solve


def run_import(args):
    if args.pages < 1 or args.max_age < 0 or (args.ids and min(args.ids) < 1):
        raise ValueError("Pages et identifiants positifs ; durée du cache positive ou nulle.")
    with closing(open_database(args.db or "data/processed/futbin_fc27.sqlite3")) as db:
        if args.file:
            print(f"{import_file(db, args.file)} versions importées depuis le fichier.")
            return 0
        with httpx.Client(
            base_url=BASE_URL,
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": "SBC-Vision/0.1 (projet etudiant)", "Accept-Encoding": "gzip"},
        ) as http:
            source = Futbin(http, float(os.getenv("FUTBIN_MIN_INTERVAL_SECONDS", "2")))
            import_catalog(db, source, args.pages, args.ids, args.refresh, args.max_age)
        print(f"{db.execute('SELECT COUNT(*) FROM cards').fetchone()[0]} versions en base.")
        print(ATTRIBUTION)
    return 0


def run_club(args):
    name = "club_demo" if args.action == "demo" else "futbin_fc27"
    with closing(open_database(args.db or f"data/processed/{name}.sqlite3")) as db:
        if args.action == "demo":
            seed_demo(db, json.loads(Path("data/fixtures/club.synthetic.json").read_text()), [])
            print("Club de démonstration entièrement fictif.")
        elif args.action == "add":
            save_item(
                db, ClubItem.model_validate_json(args.file.read_text()), confirmed=args.confirm
            )
        elif args.action == "protect":
            set_protected(db, args.instance_id, not args.remove)
        items = list_items(db, unprotected_only=getattr(args, "unprotected", False))
        for item in items:
            status = "protégée" if item["protected"] else "non protégée"
            print(f"{item['instance_id']} | {item['name']} {item['rating']} | {status}")
        print(f"{len(items)} exemplaires affichés, {len({i['card_id'] for i in items})} versions.")
    return 0


def run_solver(args):
    now = datetime.now(UTC)
    if args.demo:
        demo = json.loads(Path("data/fixtures/solver.synthetic.json").read_text())
        challenge = Challenge.model_validate(demo["challenge"])
        now = datetime.fromisoformat(demo["price_reference_at"])
    elif args.reading:
        reading = json.loads(args.reading.read_text())
        if not reading.get("ready"):
            raise ValueError("Conditions à relire : " + "; ".join(reading.get("issues", [])))
        challenge = Challenge.model_validate(reading["challenge"])
    else:
        challenge = Challenge.model_validate_json(args.challenge.read_text())
    name = "solver_demo" if args.demo else "futbin_fc27"
    with closing(open_database(args.db or f"data/processed/{name}.sqlite3")) as db:
        if args.demo:
            club = json.loads(Path("data/fixtures/club.synthetic.json").read_text())
            seed_demo(db, club, demo["extra_cards"])
            print("Défi et cartes fictifs : contrôle du fonctionnement du solveur.")
        pool = load_pool(db, challenge.market, now=now, max_age_hours=args.max_age)
    baseline, outcome = greedy(challenge, pool), solve(challenge, pool, seconds=args.seconds)
    options = alternatives(challenge, pool, outcome, limit=args.alternatives)
    print(f"Sélection simple : {baseline.status}, coût économique {baseline.total_cost}.")
    print(f"OR-Tools : {outcome.status}, coût économique {outcome.total_cost}.")
    by_key = {card.key: card for card in pool}
    for item in outcome.assignments:
        card = by_key[item.candidate_key]
        origin = "club" if card.owned else "achat suggéré"
        position = (
            challenge.positions[item.slot]
            if challenge.mode == "squad"
            else f"Élément {item.slot + 1}"
        )
        print(
            f"{position} : {card.name}, version {card.card_id}, "
            f"{origin}, valeur {card.value} ({card.key})."
        )
    print(f"Achats : {outcome.purchase_cost} ; valeur sacrifiée : {outcome.sacrifice_value}.")
    chosen = {a.candidate_key for a in baseline.assignments + outcome.assignments}
    chosen.update(
        a["candidate_key"] for option in options for a in option["solution"]["assignments"]
    )
    report = {
        "challenge": challenge.model_dump(),
        "price_reference_at": now.isoformat(),
        "baseline": baseline.model_dump(),
        "solution": outcome.model_dump(),
        "alternatives": options,
        "selected_candidates": [c.model_dump() for c in pool if c.key in chosen],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"Proposition locale : {args.output}")
    return 0 if outcome.status in {"optimal", "feasible"} else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description="OCR, catalogue, club et optimisation SBC.")
    commands = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--db", type=Path)
    market = commands.add_parser("import", parents=[common], help="Importer FUTBIN.")
    market.add_argument("--pages", type=int, default=2)
    market.add_argument("--ids", type=int, nargs="+")
    market.add_argument("--file", type=Path, help="Export JSON normalisé, sans accès réseau.")
    market.add_argument("--refresh", action="store_true")
    market.add_argument("--max-age", type=float, default=24)
    club = commands.add_parser("club", parents=[common], help="Gérer les exemplaires.")
    actions = club.add_subparsers(dest="action", required=True)
    actions.add_parser("demo")
    listing = actions.add_parser("list")
    listing.add_argument("--unprotected", action="store_true")
    protect = actions.add_parser("protect")
    protect.add_argument("instance_id")
    protect.add_argument("--remove", action="store_true")
    adding = actions.add_parser("add")
    adding.add_argument("file", type=Path)
    adding.add_argument("--confirm", action="store_true")
    solver = commands.add_parser("solve", parents=[common], help="Proposer une composition.")
    mode = solver.add_mutually_exclusive_group(required=True)
    mode.add_argument("--demo", action="store_true")
    mode.add_argument("--challenge", type=Path)
    mode.add_argument("--reading", type=Path, help="Rapport OCR ou conditions déjà vérifiées.")
    solver.add_argument("--seconds", type=float, default=5)
    solver.add_argument("--alternatives", type=int, choices=range(4), default=2)
    solver.add_argument("--max-age", type=float, default=24)
    solver.add_argument("--output", type=Path, default=Path("data/processed/solution.json"))
    ocr = commands.add_parser("ocr", parents=[common], help="Lire les régions d'une capture.")
    ocr.add_argument("image", type=Path)
    ocr.add_argument("regions", type=Path)
    ocr.add_argument("--lang", default="eng")
    ocr.add_argument("--min-confidence", type=float, default=0.75)
    ocr.add_argument("--budget", type=int)
    ocr.add_argument("--market", choices=["ps", "pc"])
    ocr.add_argument("--output", type=Path, default=Path("data/processed/ocr.json"))
    requirements = commands.add_parser(
        "conditions", parents=[common], help="Interpréter des conditions lues."
    )
    requirements.add_argument("file", type=Path)
    requirements.add_argument("--positions", nargs="*", default=[])
    requirements.add_argument("--budget", type=int, required=True)
    requirements.add_argument("--market", choices=["ps", "pc"], required=True)
    requirements.add_argument("--output", type=Path, default=Path("data/processed/conditions.json"))
    args = parser.parse_args(argv)
    try:
        if args.command == "ocr":
            from .ocr import analyze, challenge_from_ocr

            spec = OcrInput.model_validate_json(args.regions.read_text())
            with closing(open_database(args.db or "data/processed/futbin_fc27.sqlite3")) as db:
                report = analyze(args.image, spec, db, lang=args.lang, minimum=args.min_confidence)
                if args.market is not None and args.budget is not None:
                    report.update(
                        challenge_from_ocr(
                            report,
                            db,
                            market=args.market,
                            budget=args.budget,
                            minimum=args.min_confidence,
                        )
                    )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
            print(f"Lecture à vérifier : {args.output}")
            return 2 if report.get("ready") is False else 0
        if args.command == "conditions":
            from .ocr import parse_requirements

            with closing(open_database(args.db or "data/processed/futbin_fc27.sqlite3")) as db:
                report = parse_requirements(
                    args.file.read_text(),
                    db,
                    positions=args.positions,
                    market=args.market,
                    budget=args.budget,
                )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
            print(f"Conditions {'prêtes' if report['ready'] else 'à relire'} : {args.output}")
            for issue in report["issues"]:
                print(issue)
            return 0 if report["ready"] else 2
        return {"import": run_import, "club": run_club, "solve": run_solver}[args.command](args)
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error, httpx.HTTPError) as error:
        print(f"Erreur : {error}")
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
