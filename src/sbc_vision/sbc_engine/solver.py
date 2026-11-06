"""Optimisation globale, référence simple et vérification séparée."""

import time
from collections import defaultdict

from ortools.sat.python import cp_model

from .models import Assignment, Candidate, Challenge, SolverResult


def validate(challenge: Challenge, pool: list[Candidate], team: list[Assignment]) -> list[str]:
    errors = []
    expected = list(range(len(challenge.positions)))
    if sorted(item.slot for item in team) != expected:
        return ["La composition doit remplir chaque emplacement exactement une fois."]
    by_key = {card.key: card for card in pool}
    if len(by_key) != len(pool):
        return ["Les identifiants des candidats doivent être uniques."]
    if any(item.candidate_key not in by_key for item in team):
        return ["La composition référence un candidat inconnu."]
    cards = [by_key[item.candidate_key] for item in team]
    # Une seule version ou copie d'une même famille de joueur peut entrer dans l'équipe.
    if len({card.base_id for card in cards}) != len(cards):
        errors.append("Un même joueur apparaît plusieurs fois.")
    for item, card in zip(team, cards, strict=True):
        if card.protected or card.value is None:
            errors.append(f"Carte protégée ou prix inconnu : {card.key}.")
        if challenge.positions[item.slot] not in card.positions:
            errors.append(f"Poste incompatible : {card.key}.")
        if card.rating < challenge.min_card_rating:
            errors.append(f"Note individuelle insuffisante : {card.key}.")
    # Aucun zéro de substitution n'est utilisé pour une valeur inconnue.
    if any(card.value is None for card in cards):
        return errors
    if sum(card.value for card in cards if not card.owned) > challenge.budget:
        errors.append("Budget d'achat dépassé.")
    if sum(card.is_rare for card in cards) < challenge.min_rare:
        errors.append("Nombre de cartes rares insuffisant.")
    if sum(card.nation_id == challenge.nation_id for card in cards) < challenge.min_nation:
        errors.append("Quota de pays non respecté.")
    if sum(card.league_id == challenge.league_id for card in cards) < challenge.min_league:
        errors.append("Quota de ligue non respecté.")
    return errors


def eligible(challenge, pool):
    if len({card.key for card in pool}) != len(pool):
        raise ValueError("Les identifiants des candidats doivent être uniques.")
    return [
        c
        for c in pool
        if not c.protected and c.value is not None and c.rating >= challenge.min_card_rating
    ]


def result(challenge, pool, team, status, elapsed):
    errors = validate(challenge, pool, team)
    if errors:
        return SolverResult(status="unknown", errors=errors, elapsed_seconds=elapsed)
    cards = {card.key: card for card in pool}
    chosen = [cards[item.candidate_key] for item in team]
    purchase = sum(card.value for card in chosen if not card.owned)
    sacrifice = sum(card.value for card in chosen if card.owned)
    return SolverResult(
        status=status,
        assignments=team,
        purchase_cost=purchase,
        sacrifice_value=sacrifice,
        total_cost=purchase + sacrifice,
        elapsed_seconds=elapsed,
    )


def solve(challenge: Challenge, pool: list[Candidate], *, seconds=5.0) -> SolverResult:
    if not 0 < seconds <= 60:
        raise ValueError("Le délai doit être compris entre 0 et 60 secondes, zéro exclu.")
    start = time.monotonic()
    cards = eligible(challenge, pool)
    kept = {card.key for card in cards}
    excluded = [card.key for card in pool if card.key not in kept]
    model = cp_model.CpModel()
    # Une variable vaut 1 si une carte occupe un emplacement compatible.
    choices = {
        (i, slot): model.new_bool_var(f"{i}_{slot}")
        for i, card in enumerate(cards)
        for slot, position in enumerate(challenge.positions)
        if position in card.positions
    }
    by_slot = [[] for _ in challenge.positions]
    by_card = [[] for _ in cards]
    by_player = defaultdict(list)
    for (i, slot), variable in choices.items():
        by_slot[slot].append(variable)
        by_card[i].append(variable)
        by_player[cards[i].base_id].append(variable)
    for variables in by_slot:
        model.add_exactly_one(variables)
    for variables in by_player.values():
        model.add_at_most_one(variables)
    selected = [sum(variables) for variables in by_card]
    model.add(
        sum(c.value * used for c, used in zip(cards, selected, strict=True) if not c.owned)
        <= challenge.budget
    )
    for field, value, minimum in (
        ("is_rare", True, challenge.min_rare),
        ("nation_id", challenge.nation_id, challenge.min_nation),
        ("league_id", challenge.league_id, challenge.min_league),
    ):
        model.add(
            sum(used for c, used in zip(cards, selected, strict=True) if getattr(c, field) == value)
            >= minimum
        )
    # Priorité au coût, puis aux cartes non rares et enfin au nombre d'achats.
    scale = len(challenge.positions) + 1
    model.minimize(
        sum(
            ((c.value * scale + int(c.is_rare)) * scale + int(not c.owned)) * used
            for c, used in zip(cards, selected, strict=True)
        )
    )
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = seconds
    solver.parameters.num_search_workers = 1
    status = solver.solve(model)
    if status == cp_model.MODEL_INVALID:
        raise ValueError(solver.solution_info())
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return SolverResult(
            status="infeasible" if status == cp_model.INFEASIBLE else "unknown",
            elapsed_seconds=time.monotonic() - start,
            excluded_keys=excluded,
        )
    team = sorted(
        [
            Assignment(slot=slot, candidate_key=cards[i].key)
            for (i, slot), var in choices.items()
            if solver.value(var)
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
    cards = sorted(
        eligible(challenge, pool), key=lambda c: (c.value, c.is_rare, not c.owned, c.key)
    )
    team, used, purchase = [], set(), 0
    for slot, position in enumerate(challenge.positions):
        card = next(
            (
                c
                for c in cards
                if position in c.positions
                and c.base_id not in used
                and purchase + (0 if c.owned else c.value) <= challenge.budget
            ),
            None,
        )
        if card is None:
            # Un échec glouton ne prouve pas que le problème est impossible.
            return SolverResult(
                status="unknown",
                errors=["La sélection simple est bloquée."],
                elapsed_seconds=time.monotonic() - start,
            )
        team.append(Assignment(slot=slot, candidate_key=card.key))
        used.add(card.base_id)
        purchase += 0 if card.owned else card.value
    return result(challenge, pool, team, "feasible", time.monotonic() - start)
