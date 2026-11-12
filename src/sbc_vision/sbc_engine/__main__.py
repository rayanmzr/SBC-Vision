"""Commande commune : python -m sbc_vision.sbc_engine --help."""

import argparse
import json
import os
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import httpx

from .models import Challenge, ClubItem, OcrInput
from .players import (
    ATTRIBUTION,
    BASE_URL,
    Futbin,
    confirm_readings,
    import_catalog,
    import_file,
    import_readings,
    list_items,
    load_pool,
    open_database,
    save_item,
    seed_demo,
    set_protected,
    sync_scan,
)
from .solver import alternatives, greedy, shopping_list, solve, verification


def run_import(args):
    if (args.ids or args.file or args.reading) and args.quality != "all":
        raise ValueError("Le filtre de qualité s'applique à l'index, pas aux IDs ou aux fichiers.")
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
            if args.reading:
                report = import_readings(
                    db,
                    source,
                    json.loads(args.reading.read_text()),
                    pages=args.pages,
                    refresh=args.refresh,
                )
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
                matched = sum(bool(c["candidate_ids"]) for c in report["cards"])
                print(f"{matched}/{len(report['cards'])} lectures avec candidats ; à confirmer.")
                for card in report["cards"]:
                    if len(card["candidate_ids"]) > 1:
                        print(
                            f"Version ambiguë : {card['reading']['name']} — {card['candidate_ids']}"
                        )
                print(f"Rapprochements locaux : {args.output}")
            else:
                import_catalog(
                    db,
                    source,
                    args.pages,
                    args.ids,
                    args.refresh,
                    args.max_age,
                    quality=args.quality,
                )
        print(f"{db.execute('SELECT COUNT(*) FROM cards').fetchone()[0]} versions en base.")
        print(ATTRIBUTION)
    return 0


def run_club(args):
    demo = args.action == "demo" or getattr(args, "demo", False)
    name = "club_demo" if demo else "futbin_fc27"
    if args.action == "scan":
        if bool(args.file) == args.demo:
            raise ValueError("Choisir un fichier de captures ou --demo.")
        if args.demo:
            name = "club_scan_demo"
    with closing(open_database(args.db or f"data/processed/{name}.sqlite3")) as db:
        if args.action == "scan":
            if args.demo:
                fixture = json.loads(Path("data/fixtures/club.synthetic.json").read_text())
                seed_demo(db, {**fixture, "items": []}, [])
                captures = fixture["scan"]
                print("Démo fictive : rapports, choix et suivi des exemplaires simulés.")
            else:
                captures = json.loads(args.file.read_text())
                for capture in captures:
                    if isinstance(capture["report"], str):
                        path = args.file.parent / capture["report"]
                        capture["report"] = json.loads(path.read_text())
            result = sync_scan(db, captures, confirmed=args.confirm or args.demo)
            scan_name = "club_scan_demo" if args.demo else "club_scan"
            output = args.output or Path(f"data/processed/{scan_name}.json")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
            print(
                f"{result['captures']} captures, {result['observations']} observations : "
                f"{result['items']} exemplaires distincts ; "
                f"observations répétées : {result['reobserved']}."
            )
            print(
                f"Enregistrés : {result['saved']} ; lectures en attente : {len(result['pending'])}."
            )
            print(f"Bilan local : {output}")
            return 0
        elif args.action == "demo":
            seed_demo(db, json.loads(Path("data/fixtures/club.synthetic.json").read_text()), [])
            print("Club de démonstration entièrement fictif.")
        elif args.action == "add":
            save_item(
                db, ClubItem.model_validate_json(args.file.read_text()), confirmed=args.confirm
            )
        elif args.action == "protect":
            set_protected(db, args.instance_id, not args.remove)
        elif args.action == "sync":
            count = confirm_readings(
                db,
                json.loads(args.reading.read_text()),
                json.loads(args.choices.read_text()),
                confirmed=args.confirm,
            )
            print(f"{count} lectures confirmées enregistrées.")
        items = list_items(db, unprotected_only=getattr(args, "unprotected", False))
        for item in items:
            status = "protégée" if item["protected"] else "non protégée"
            print(f"{item['instance_id']} | {item['name']} {item['rating']} | {status}")
        print(f"{len(items)} exemplaires affichés, {len({i['card_id'] for i in items})} versions.")
    return 0


def run_solver(args, *, now=None):
    now = now or datetime.now(UTC)
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
    preferences = {
        key: getattr(args, key)
        for key in ("budget", "max_card_value")
        if getattr(args, key, None) is not None
    }
    if preferences:
        challenge = Challenge.model_validate({**challenge.model_dump(), **preferences})
    print(f"Budget d'achat : {challenge.budget} crédits.")
    if challenge.max_card_value is not None:
        print(f"Valeur maximale par carte : {challenge.max_card_value} crédits (club et achats).")
    name = "solver_demo" if args.demo else "futbin_fc27"
    with closing(open_database(args.db or f"data/processed/{name}.sqlite3")) as db:
        if args.demo:
            club = json.loads(Path("data/fixtures/club.synthetic.json").read_text())
            seed_demo(db, club, demo["extra_cards"])
            print("Défi et cartes fictifs : contrôle du fonctionnement du solveur.")
        pool = load_pool(db, challenge.market, now=now, max_age_hours=args.max_age)
    baseline, outcome = greedy(challenge, pool), solve(challenge, pool, seconds=args.seconds)
    options = alternatives(challenge, pool, outcome, limit=args.alternatives)
    purchases = shopping_list(challenge, pool, outcome)
    checked = verification(challenge, pool, outcome)
    for label, result in [("Sélection simple", baseline), ("OR-Tools", outcome)]:
        cost = (
            f"coût économique {result.total_cost}"
            if result.total_cost is not None
            else "sans proposition"
        )
        print(f"{label} : {result.status}, {cost}.")
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
    if outcome.purchase_cost is not None:
        print(f"Achats : {outcome.purchase_cost} ; valeur sacrifiée : {outcome.sacrifice_value}.")
    if purchases:
        for item in purchases["items"]:
            print(
                f"À acheter : {item['quantity']} × {item['name']}, version {item['card_id']}, "
                f"plafond {item['max_unit_price']} crédits par carte."
            )
    if checked:
        print("Vérification locale des conditions (hors validation EA) :")
        for check in checked["checks"]:
            op = {"min": ">=", "max": "<=", "exact": "="}[check["op"]]
            label = check["text"] or check["metric"]
            print(f"  OK | {label} : obtenu {check['actual']} ; attendu {op} {check['value']}.")
    chosen = {a.candidate_key for a in baseline.assignments + outcome.assignments}
    chosen.update(
        a["candidate_key"] for option in options for a in option["solution"]["assignments"]
    )
    report = {
        "challenge": challenge.model_dump(),
        "price_reference_at": now.isoformat(),
        "baseline": baseline.model_dump(),
        "solution": outcome.model_dump(),
        "shopping_list": purchases,
        "verification": checked,
        "alternatives": options,
        "selected_candidates": [c.model_dump() for c in pool if c.key in chosen],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"Proposition locale : {args.output}")
    return 0 if outcome.status in {"optimal", "feasible"} else 2


def run_demo(args):
    from .ocr import analyze, challenge_from_ocr, evaluate, evaluation_demo

    club = json.loads(Path("data/fixtures/club.synthetic.json").read_text())
    demo = json.loads(Path("data/fixtures/solver.synthetic.json").read_text())
    if args.complex:
        demo = demo["complex"]
        club = demo["club"]
    folder = args.directory or Path(
        "data/processed/pipeline_complex_demo" if args.complex else "data/processed/pipeline_demo"
    )
    cards = {card["id"]: card for card in club["catalogue"]}
    args.db, args.reading, args.output = [
        folder / name for name in ("club.sqlite3", "reading.json", "solution.json")
    ]
    print("Parcours fictif : régions annotées et confirmations simulées, sans connexion à EA.")
    with closing(open_database(args.db)) as db:
        # Seul le catalogue est préparé ; les exemplaires passent ensuite par l'OCR.
        seed_demo(db, {**club, "items": []}, demo["extra_cards"])
        args.output.unlink(missing_ok=True)  # Retirer la proposition d'un précédent essai.
        labels, choices = [], {}
        for i, item in enumerate(club["items"], 1):
            element_id, card = f"card-{i}", cards[item["card_id"]]
            for field in ("name", "rating", "position"):
                labels.append((element_id, field, str(card[field]).upper()))
            choices[element_id] = {
                k: item[k] for k in ("instance_id", "card_id", "protected", "tradeable")
            }
        labels.extend(
            (f"slot-{i}", "slots", position)
            for i, position in enumerate(demo["challenge"]["positions"])
        )
        labels.extend(
            (f"condition-{i}", "requirements", line)
            for i, line in enumerate(demo["requirements_text"].splitlines())
        )
        raw, expected = evaluation_demo(folder, labels=labels)
        spec = OcrInput(
            capture_id=raw["capture_id"],
            regions=[
                {k: region[k] for k in ("element_id", "field", "bbox")}
                for region in expected["regions"]
            ],
        )
        report = analyze(folder / "ocr_demo.png", spec, db, regions=raw["regions"])
        report.update(
            challenge_from_ocr(
                report, db, market=demo["challenge"]["market"], budget=demo["challenge"]["budget"]
            )
        )
        for name, data in [
            ("reading.json", report),
            ("choices.json", choices),
            ("metrics.json", evaluate(report, expected)),
        ]:
            (folder / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        if not report["ready"]:
            print("Conditions à relire : " + "; ".join(report["issues"]))
            return 2
        print(
            f"Conditions lues : {len(report['challenge']['conditions'])} contraintes "
            f"et qualité {report['challenge']['card_level']}."
        )
        confirm_readings(db, report, choices, confirmed=True)
        print(f"OCR → inventaire : {len(list_items(db))} exemplaires, protections conservées.")
    # La démo conserve la date de ses prix fictifs, sans rajeunir des relevés réels.
    return run_solver(args, now=datetime.fromisoformat(demo["price_reference_at"]))


def main(argv=None):
    parser = argparse.ArgumentParser(description="OCR, catalogue, club et optimisation SBC.")
    commands = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--db", type=Path)
    demo = commands.add_parser("demo", help="Tester image, inventaire et solveur ensemble.")
    demo.add_argument("--directory", type=Path)
    demo.add_argument(
        "--complex", action="store_true", help="Onze joueurs et dix conditions fictives."
    )
    demo.add_argument("--max-card-value", type=int, default=1000)
    demo.set_defaults(demo=False, seconds=5, alternatives=2, max_age=24)
    market = commands.add_parser("import", parents=[common], help="Importer FUTBIN.")
    market.add_argument("--pages", type=int, default=2)
    market.add_argument("--quality", choices=["all", "gold", "silver", "bronze"], default="all")
    imports = market.add_mutually_exclusive_group()
    imports.add_argument("--ids", type=int, nargs="+")
    imports.add_argument("--file", type=Path, help="Export JSON normalisé, sans accès réseau.")
    imports.add_argument("--reading", type=Path, help="Chercher les cartes d'un rapport OCR.")
    market.add_argument(
        "--output", type=Path, default=Path("data/processed/catalogue_matches.json")
    )
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
    sync = actions.add_parser("sync", help="Enregistrer les versions choisies d'un rapport OCR.")
    sync.add_argument("reading", type=Path)
    sync.add_argument("choices", type=Path)
    sync.add_argument("--confirm", action="store_true")
    scan = actions.add_parser("scan", help="Réunir les observations de plusieurs captures.")
    scan.add_argument("file", type=Path, nargs="?")
    scan.add_argument("--demo", action="store_true")
    scan.add_argument("--confirm", action="store_true")
    scan.add_argument("--output", type=Path)
    solver = commands.add_parser("solve", parents=[common], help="Proposer une composition.")
    mode = solver.add_mutually_exclusive_group(required=True)
    mode.add_argument("--demo", action="store_true")
    mode.add_argument("--challenge", type=Path)
    mode.add_argument("--reading", type=Path, help="Rapport OCR ou conditions déjà vérifiées.")
    solver.add_argument("--seconds", type=float, default=5)
    solver.add_argument("--alternatives", type=int, choices=range(4), default=2)
    solver.add_argument("--max-age", type=float, default=24)
    solver.add_argument("--budget", type=int, help="Budget d'achat remplaçant celui du rapport lu.")
    solver.add_argument(
        "--max-card-value", type=int, help="Valeur maximale par carte, club inclus."
    )
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
    evaluation = commands.add_parser("evaluate", help="Mesurer l'OCR avec des textes annotés.")
    inputs = evaluation.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--demo", action="store_true")
    inputs.add_argument("--reading", type=Path)
    evaluation.add_argument("--expected", type=Path)
    evaluation.add_argument("--lang", default="eng")
    evaluation.add_argument("--min-confidence", type=float, default=0.75)
    evaluation.add_argument("--output", type=Path, default=Path("data/processed/ocr_metrics.json"))
    args = parser.parse_args(argv)
    try:
        if args.command == "evaluate":
            from .ocr import evaluate, evaluation_demo

            if args.demo:
                if args.expected:
                    raise ValueError("La démo génère ses propres annotations.")
                report, expected = evaluation_demo(args.output.parent, lang=args.lang)
                print("Image et textes fictifs : ceci ne mesure pas la qualité sur EA FC.")
            else:
                if not args.expected:
                    raise ValueError("Fournir les textes annotés avec --expected.")
                report, expected = (
                    json.loads(args.reading.read_text()),
                    json.loads(args.expected.read_text()),
                )
            metrics = evaluate(report, expected, minimum=args.min_confidence)
            if args.demo:
                metrics["data_kind"] = "synthetic"
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n")
            values = metrics["summary"]
            print(
                f"{values['fields']} champs ; CER {values['cer']:.1%} ; "
                f"exacts {values['exact_accuracy']:.1%} ; inconnus {values['unknown_rate']:.1%}."
            )
            print(f"Mesures locales : {args.output}")
            return 0
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
        return {"import": run_import, "club": run_club, "solve": run_solver, "demo": run_demo}[
            args.command
        ](args)
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error, httpx.HTTPError) as error:
        print(f"Erreur : {error}")
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
