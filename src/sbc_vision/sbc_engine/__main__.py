"""Commande commune : python -m sbc_vision.sbc_engine --help."""

import argparse
import json
import os
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import httpx

from .catalogue import ATTRIBUTION, BASE_URL, Futbin, import_catalog, open_database
from .inventory import list_items, load_pool, save_item, seed_demo, set_protected
from .models import Challenge, ClubItem
from .solver import greedy, solve


def run_import(args):
    if args.pages < 1 or args.max_age < 0 or (args.ids and min(args.ids) < 1):
        raise ValueError("Pages et identifiants positifs ; durée du cache positive ou nulle.")
    with closing(open_database(args.db or "data/processed/futbin_fc27.sqlite3")) as db:
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
    print(f"Sélection simple : {baseline.status}, coût économique {baseline.total_cost}.")
    print(f"OR-Tools : {outcome.status}, coût économique {outcome.total_cost}.")
    by_key = {card.key: card for card in pool}
    for item in outcome.assignments:
        card = by_key[item.candidate_key]
        origin = "club" if card.owned else "achat suggéré"
        print(
            f"{challenge.positions[item.slot]} : {card.name}, version {card.card_id}, "
            f"{origin}, valeur {card.value} ({card.key})."
        )
    print(f"Achats : {outcome.purchase_cost} ; valeur sacrifiée : {outcome.sacrifice_value}.")
    chosen = {a.candidate_key for a in baseline.assignments + outcome.assignments}
    report = {
        "challenge": challenge.model_dump(),
        "price_reference_at": now.isoformat(),
        "baseline": baseline.model_dump(),
        "solution": outcome.model_dump(),
        "selected_candidates": [c.model_dump() for c in pool if c.key in chosen],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"Proposition locale : {args.output}")
    return 0 if outcome.assignments else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description="OCR, catalogue, club et optimisation SBC.")
    commands = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--db", type=Path)
    market = commands.add_parser("import", parents=[common], help="Importer FUTBIN.")
    market.add_argument("--pages", type=int, default=2)
    market.add_argument("--ids", type=int, nargs="+")
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
    solver.add_argument("--seconds", type=float, default=5)
    solver.add_argument("--max-age", type=float, default=24)
    solver.add_argument("--output", type=Path, default=Path("data/processed/solution.json"))
    args = parser.parse_args(argv)
    try:
        return {"import": run_import, "club": run_club, "solve": run_solver}[args.command](args)
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error, httpx.HTTPError) as error:
        print(f"Erreur : {error}")
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
