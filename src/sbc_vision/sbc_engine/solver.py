"""Contraintes dynamiques, optimisation globale et vérification en Python."""

import time
from collections import Counter, defaultdict
from fractions import Fraction

from ortools.sat.python import cp_model

from .models import Assignment, Candidate, Challenge, SolverResult

THRESHOLDS = {"club_id": (2, 4, 7), "nation_id": (2, 5, 8), "league_id": (3, 5, 8)}


def compare(actual, op, expected):
    return {"min": actual >= expected, "max": actual <= expected, "exact": actual == expected}[op]


def team_rating(ratings):
    # Référence à onze joueurs : correction des notes au-dessus de la moyenne, puis arrondi.
    average = Fraction(sum(ratings), 11)
    corrected = sum(ratings) + sum(max(Fraction(r) - average, 0) for r in ratings)
    return int(corrected + Fraction(1, 2)) // 11


def chemistry(cards):
    counts = {field: Counter(getattr(c, field) for c in cards) for field in THRESHOLDS}
    return sum(
        min(
            3,
            sum(
                counts[field][getattr(c, field)] >= threshold
                for field, thresholds in THRESHOLDS.items()
                for threshold in thresholds
            ),
        )
        for c in cards
    )


def metric(rule, cards, challenge):
    field = {"nation": "nation_id", "league": "league_id", "club": "club_id"}
    name = rule.metric
    if name == "players":
        return len(cards)
    if name == "item_score":
        return challenge.score_progress + sum(c.item_score for c in cards)
    if name == "rare":
        return sum(c.is_rare for c in cards)
    if name == "quality":
        return sum(c.card_level == rule.target for c in cards)
    if name == "rated":
        return sum(c.rating >= rule.target for c in cards)
    if name in field:
        return sum(getattr(c, field[name]) == rule.target for c in cards)
    if name in {"nations", "leagues", "clubs"}:
        return len({getattr(c, field[name[:-1]]) for c in cards})
    if name.startswith("same_"):
        return max(Counter(getattr(c, field[name[5:]]) for c in cards).values(), default=0)
    return team_rating([c.rating for c in cards]) if name == "team_rating" else chemistry(cards)


def eligible(challenge, pool):
    if len({c.key for c in pool}) != len(pool):
        raise ValueError("Les identifiants des candidats doivent être uniques.")
    rules = challenge.conditions
    need_score = any(r.metric == "item_score" for r in rules)
    need_club = any(r.metric in {"club", "clubs", "same_club", "chemistry"} for r in rules)
    return [
        c
        for c in pool
        if not c.protected
        and c.value is not None
        and (challenge.max_card_value is None or c.value <= challenge.max_card_value)
        and (challenge.card_level is None or c.card_level == challenge.card_level)
        and (not need_score or c.item_score is not None)
        and (not need_club or c.club_id is not None)
        and (not any(r.metric == "quality" for r in rules) or c.card_level is not None)
        and (not any(r.metric == "chemistry" for r in rules) or c.chemistry_kind == "standard")
        and all(compare(c.rating, r.op, r.value) for r in rules if r.metric == "rating")
    ]


def validate(challenge: Challenge, pool: list[Candidate], team: list[Assignment]) -> list[str]:
    expected = len(challenge.positions) if challenge.mode == "squad" else len(team)
    if sorted(a.slot for a in team) != list(range(expected)) or len(team) > challenge.max_items:
        return ["Chaque emplacement doit être rempli une fois, dans la limite d'exemplaires."]
    by_key = {c.key: c for c in pool}
    if len(by_key) != len(pool):
        return ["Les identifiants des candidats doivent être uniques."]
    if any(a.candidate_key not in by_key for a in team):
        return ["La composition référence un candidat inconnu."]
    cards, errors = [by_key[a.candidate_key] for a in team], []
    if challenge.mode == "squad" and len({c.base_id for c in cards}) != len(cards):
        errors.append("Un même joueur apparaît plusieurs fois.")
    counts = Counter(a.candidate_key for a in team)
    if any(
        n > (1 if challenge.mode == "squad" else by_key[k].max_quantity) for k, n in counts.items()
    ):
        errors.append("La quantité disponible d'un candidat est dépassée.")
    for assignment, card in zip(team, cards, strict=True):
        if card.protected or card.value is None:
            errors.append(f"Carte protégée ou prix inconnu : {card.key}.")
        if (
            challenge.max_card_value is not None
            and card.value is not None
            and card.value > challenge.max_card_value
        ):
            errors.append(f"Valeur maximale par carte dépassée : {card.key}.")
        if challenge.mode == "squad" and challenge.positions[assignment.slot] not in card.positions:
            errors.append(f"Poste incompatible : {card.key}.")
        if challenge.card_level is not None and card.card_level != challenge.card_level:
            errors.append(f"Qualité incompatible : {card.key}.")
    if any(c.value is None for c in cards):
        return errors
    if sum(c.value for c in cards if not c.owned) > challenge.budget:
        errors.append("Budget d'achat dépassé.")
    for rule in challenge.conditions:
        if rule.metric == "rating":
            valid = all(compare(c.rating, rule.op, rule.value) for c in cards)
        elif rule.metric == "item_score" and any(c.item_score is None for c in cards):
            valid = False
        elif rule.metric == "chemistry" and any(c.chemistry_kind != "standard" for c in cards):
            valid = False
        elif rule.metric in {"club", "clubs", "same_club"} and any(
            c.club_id is None for c in cards
        ):
            valid = False
        elif rule.metric == "quality" and any(c.card_level is None for c in cards):
            valid = False
        else:
            valid = compare(metric(rule, cards, challenge), rule.op, rule.value)
        if not valid:
            errors.append(f"Condition non respectée : {rule.text or rule.metric}.")
    return errors


def result(challenge, pool, team, status, elapsed):
    errors = validate(challenge, pool, team)
    if errors:
        return SolverResult(status="unknown", errors=errors, elapsed_seconds=elapsed)
    by_key = {c.key: c for c in pool}
    cards = [by_key[a.candidate_key] for a in team]
    purchase = sum(c.value for c in cards if not c.owned)
    sacrifice = sum(c.value for c in cards if c.owned)
    return SolverResult(
        status=status,
        assignments=team,
        purchase_cost=purchase,
        sacrifice_value=sacrifice,
        total_cost=purchase + sacrifice,
        elapsed_seconds=elapsed,
    )


def expression(rule, cards, used, model, challenge, ratings):
    name = rule.metric
    if name == "players":
        return sum(used)
    if name == "item_score":
        return challenge.score_progress + sum(
            c.item_score * n for c, n in zip(cards, used, strict=True)
        )
    if name in {"rare", "quality", "rated", "nation", "league", "club"}:
        return sum(n for c, n in zip(cards, used, strict=True) if metric(rule, [c], challenge))
    if name == "team_rating":
        # 242 = 2 × 11² : calcul entier équivalent à la correction et à l'arrondi.
        total, excess = sum(ratings), []
        for rating in ratings:
            value = model.new_int_var(0, 1089, "excess")
            model.add_max_equality(value, [11 * rating - total, 0])
            excess.append(value)
        grade = model.new_int_var(0, 99, "team_rating")
        model.add_division_equality(grade, 2 * (11 * total + sum(excess)) + 11, 242)
        return grade
    if name == "chemistry":
        levels = {}
        for field, thresholds in THRESHOLDS.items():
            groups = defaultdict(list)
            for c, n in zip(cards, used, strict=True):
                groups[getattr(c, field)].append(n)
            for key, values in groups.items():
                levels[field, key] = []
                for threshold in thresholds:
                    # Chaque seuil est lié au compte dans les deux sens.
                    flag = model.new_bool_var("threshold")
                    model.add(sum(values) >= threshold).only_enforce_if(flag)
                    model.add(sum(values) < threshold).only_enforce_if(flag.Not())
                    levels[field, key].append(flag)
        profiles = defaultdict(list)
        for c, n in zip(cards, used, strict=True):
            profiles[c.club_id, c.nation_id, c.league_id].append(n)
        contributions = []
        for profile, values in profiles.items():
            # Un profil commun partage ses points ; chaque joueur est plafonné à trois.
            level = model.new_int_var(0, 3, "chemistry")
            count = model.new_int_var(0, 11, "profile_count")
            contribution = model.new_int_var(0, 33, "contribution")
            model.add(count == sum(values))
            model.add_min_equality(
                level,
                [
                    3,
                    sum(
                        f
                        for field, key in zip(THRESHOLDS, profile, strict=True)
                        for f in levels[field, key]
                    ),
                ],
            )
            model.add_multiplication_equality(contribution, [level, count])
            contributions.append(contribution)
        return sum(contributions)
    # Compter des groupes distincts ou le plus grand groupe (même pays/ligue/club).
    field = {"nations": "nation_id", "leagues": "league_id", "clubs": "club_id"}.get(name)
    field = field or f"{name[5:]}_id"
    groups = defaultdict(list)
    for c, n in zip(cards, used, strict=True):
        groups[getattr(c, field)].append(n)
    if name.startswith("same_"):
        maximum = model.new_int_var(0, challenge.max_items, "largest_group")
        model.add_max_equality(maximum, [sum(g) for g in groups.values()] or [0])
        return maximum
    flags = []
    for group in groups.values():
        flag = model.new_bool_var("present")
        model.add(sum(group) >= 1).only_enforce_if(flag)
        model.add(sum(group) == 0).only_enforce_if(flag.Not())
        flags.append(flag)
    return sum(flags)


def solve(challenge: Challenge, pool: list[Candidate], *, seconds=5.0) -> SolverResult:
    if not 0 < seconds <= 60:
        raise ValueError("Le délai doit être compris entre 0 et 60 secondes, zéro exclu.")
    start, cards, model = time.monotonic(), eligible(challenge, pool), cp_model.CpModel()
    kept = {c.key for c in cards}
    excluded = [c.key for c in pool if c.key not in kept]
    choices, ratings = {}, []
    if challenge.mode == "score":
        # Les copies sont autorisées jusqu'à la quantité connue, jamais au-delà.
        used = [model.new_int_var(0, c.max_quantity, c.key) for c in cards]
    else:
        by_slot, by_card, by_player = defaultdict(list), [[] for _ in cards], defaultdict(list)
        for i, card in enumerate(cards):
            for slot, position in enumerate(challenge.positions):
                if position in card.positions:
                    variable = model.new_bool_var(f"{i}_{slot}")
                    choices[i, slot] = variable
                    by_slot[slot].append((i, variable))
                    by_card[i].append(variable)
                    by_player[card.base_id].append(variable)
        for slot in range(len(challenge.positions)):
            model.add_exactly_one(v for i, v in by_slot[slot])
            ratings.append(sum(cards[i].rating * v for i, v in by_slot[slot]))
        for variables in by_player.values():
            model.add_at_most_one(variables)
        used = [sum(variables) for variables in by_card]
    model.add(sum(used) <= challenge.max_items)
    model.add(
        sum(c.value * n for c, n in zip(cards, used, strict=True) if not c.owned)
        <= challenge.budget
    )
    cache = {}
    for rule in challenge.conditions:
        if rule.metric == "rating":
            continue  # Les notes individuelles ont déjà filtré les candidats.
        key = rule.metric, rule.target
        if key not in cache:
            cache[key] = expression(rule, cards, used, model, challenge, ratings)
        model.add(
            {
                "min": cache[key] >= rule.value,
                "max": cache[key] <= rule.value,
                "exact": cache[key] == rule.value,
            }[rule.op]
        )
    scale = (len(challenge.positions) if challenge.mode == "squad" else challenge.max_items) + 1
    model.minimize(
        sum(
            ((c.value * scale + int(c.is_rare)) * scale + int(not c.owned)) * n
            for c, n in zip(cards, used, strict=True)
        )
    )
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds, solver.parameters.num_search_workers = seconds, 1
    status = solver.solve(model)
    if status == cp_model.MODEL_INVALID:
        raise ValueError(solver.solution_info())
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return SolverResult(
            status="infeasible" if status == cp_model.INFEASIBLE else "unknown",
            elapsed_seconds=time.monotonic() - start,
            excluded_keys=excluded,
        )
    if challenge.mode == "score":
        keys = [c.key for c, n in zip(cards, used, strict=True) for _ in range(solver.value(n))]
        team = [Assignment(slot=i, candidate_key=k) for i, k in enumerate(keys)]
    else:
        team = sorted(
            [
                Assignment(slot=s, candidate_key=cards[i].key)
                for (i, s), v in choices.items()
                if solver.value(v)
            ],
            key=lambda a: a.slot,
        )
    outcome = result(
        challenge,
        pool,
        team,
        "optimal" if status == cp_model.OPTIMAL else "feasible",
        time.monotonic() - start,
    )
    outcome.excluded_keys = excluded
    return outcome


def greedy(challenge: Challenge, pool: list[Candidate]) -> SolverResult:
    start = time.monotonic()
    if challenge.mode == "score" and not validate(challenge, pool, []):
        return result(challenge, pool, [], "feasible", time.monotonic() - start)
    cards = sorted(
        eligible(challenge, pool),
        key=lambda c: (
            c.value / (c.item_score if challenge.mode == "score" else 1),
            c.is_rare,
            not c.owned,
            c.key,
        ),
    )
    team, used, purchase = [], set(), 0
    positions = challenge.positions if challenge.mode == "squad" else [None] * challenge.max_items
    for slot, position in enumerate(positions):
        if challenge.mode == "score" and team and not validate(challenge, pool, team):
            break
        card = next(
            (
                c
                for c in cards
                if (position is None or position in c.positions)
                and (
                    c.base_id not in used
                    if position
                    else sum(a.candidate_key == c.key for a in team) < c.max_quantity
                )
                and purchase + (0 if c.owned else c.value) <= challenge.budget
            ),
            None,
        )
        if card is None:
            return SolverResult(
                status="unknown",
                errors=["La sélection simple est bloquée."],
                elapsed_seconds=time.monotonic() - start,
            )
        team.append(Assignment(slot=slot, candidate_key=card.key))
        used.add(card.base_id)
        purchase += 0 if card.owned else card.value
    return result(challenge, pool, team, "feasible", time.monotonic() - start)


def shopping_list(challenge, pool, solution):
    if solution.status not in {"optimal", "feasible"}:
        return None
    if errors := validate(challenge, pool, solution.assignments):
        raise ValueError("Liste d'achats refusée : " + "; ".join(errors))
    by_key = {card.key: card for card in pool}
    quantities = Counter(a.candidate_key for a in solution.assignments)
    items = []
    for key, quantity in quantities.items():
        card = by_key[key]
        if card.owned:
            continue
        items.append(
            {
                **card.model_dump(
                    include={
                        "card_id",
                        "name",
                        "rating",
                        "positions",
                        "nation_id",
                        "league_id",
                        "club_id",
                        "card_level",
                        "is_rare",
                        "source_url",
                        "observed_at",
                    }
                ),
                "candidate_key": key,
                "quantity": quantity,
                "quoted_unit_price": card.value,
                "max_unit_price": card.value,
                "estimated_total": card.value * quantity,
                "slots": [a.slot for a in solution.assignments if a.candidate_key == key],
            }
        )
    # Chaque plafond reprend le prix retenu : la marge du budget n'est pas allouée plusieurs fois.
    cost = sum(item["estimated_total"] for item in items)
    return {
        "market": challenge.market,
        "items": items,
        "estimated_cost": cost,
        "remaining_budget": challenge.budget - cost,
    }


def alternatives(challenge, pool, solution, *, limit=2):
    """Recalculer toute l'équipe en écartant une version, au plus trois fois."""
    if not 0 <= limit <= 3:
        raise ValueError("Demander entre zéro et trois alternatives.")
    by_key = {c.key: c for c in pool}
    versions = list(dict.fromkeys(by_key[a.candidate_key].card_id for a in solution.assignments))
    proposals, seen = [], set()
    for card_id in versions[:limit]:
        outcome = solve(challenge, [c for c in pool if c.card_id != card_id], seconds=2)
        signature = tuple(a.candidate_key for a in outcome.assignments)
        if outcome.status in {"optimal", "feasible"} and signature not in seen:
            seen.add(signature)
            proposals.append(
                {
                    "excluded_card_id": card_id,
                    "solution": outcome.model_dump(),
                    "shopping_list": shopping_list(challenge, pool, outcome),
                }
            )
    return proposals
