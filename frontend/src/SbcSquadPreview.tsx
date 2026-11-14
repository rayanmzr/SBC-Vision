import { useState, type CSSProperties } from 'react';
import { StadiumPitch } from './design-a1/StadiumKit';
import type { SolverReport } from './lib/sbc-report';
import { credits } from './lib/sbc-report';
import portrait from './design-a1/assets/player-silhouette.svg';

import { squadLayout } from './lib/squad-layout';
import { purchases } from './lib/sbc-report';
import { StadiumIcon } from './design-a1/StadiumKit';

export default function SbcSquadPreview({
    report,
    sourceLabel = 'Rapport',
    shoppingOpen = false,
    onShopping,
}: {
    report: SolverReport;
    sourceLabel?: string;
    shoppingOpen?: boolean;
    onShopping?: () => void;
}) {
    const [chosen, setChosen] = useState<string | null>(null);
    const layout = squadLayout(report);
    if (!layout) return null;
    const { placements, compact, formation } = layout;
    const byKey = new Map(report.selected_candidates.map((card) => [card.key, card]));
    const assignments = report.solution.assignments!;
    const shopping = purchases(report);
    const quantity = shopping.reduce((total, item) => total + item.quantity, 0);
    const amount = (value: number | null | undefined) =>
        value == null ? '—' : value.toLocaleString('fr-FR').replaceAll('\u202f', '\u00a0');
    const amountStyle = (value: number | null | undefined) =>
        ({ '--amount-characters': amount(value).length }) as CSSProperties;
    const selected =
        placements.find(({ player }) => player.id === chosen)?.player ??
        placements.find(({ player }) => player.origin === 'club' && player.position === 'CM')
            ?.player ??
        placements[0].player;
    const candidate = byKey.get(
        assignments.find(({ slot }) => String(slot) === selected.id)!.candidate_key,
    )!;
    return (
        <section className="squad-hero" aria-label="Aperçu de l’équipe du rapport">
            <header className="squad-hero-heading">
                <h1>ÉQUIPE PROPOSÉE</h1>
                <span className="stadium-demo-label">{sourceLabel}</span>
            </header>
            <div className="stadium-squad-visual" data-small-squad={compact}>
                <StadiumPitch
                    placements={placements}
                    formation={formation}
                    selectedId={selected.id}
                    onSelect={setChosen}
                />
                <div className="stadium-selected" aria-live="polite">
                    <img src={portrait} alt="" />
                    <strong title={`${selected.rating} · ${selected.name} · ${selected.position}`}>
                        {selected.rating} · {selected.name} · {selected.position}
                    </strong>
                    <span
                        className={`stadium-origin ${selected.origin === 'purchase' ? 'stadium-origin-purchase' : ''}`}
                    >
                        {selected.origin === 'club' ? 'Club' : 'Achat'}
                    </span>
                </div>
            </div>
            <div className="stadium-costs" role="group" aria-label="Coûts du rapport, en crédits">
                <div>
                    <span>Achats</span>
                    <strong
                        aria-label={`Achats suggérés : ${credits(report.solution.purchase_cost)}`}
                        style={amountStyle(report.solution.purchase_cost)}
                    >
                        {amount(report.solution.purchase_cost)}
                    </strong>
                </div>
                <div>
                    <span>Valeur club</span>
                    <strong
                        aria-label={`Valeur des cartes utilisées : ${credits(report.solution.sacrifice_value)}`}
                        style={amountStyle(report.solution.sacrifice_value)}
                    >
                        {amount(report.solution.sacrifice_value)}
                    </strong>
                </div>
                <div className="stadium-total">
                    <span>Total</span>
                    <strong
                        aria-label={`Coût économique total : ${credits(report.solution.total_cost)}`}
                        style={amountStyle(report.solution.total_cost)}
                    >
                        {amount(report.solution.total_cost)}
                    </strong>
                </div>
            </div>
            <div className="stadium-budget-line">
                <span className="stadium-budget">
                    Budget achats : {amount(report.challenge.budget)}
                </span>
                <span className="stadium-purchases-caption">
                    <StadiumIcon name="bag" />
                    Achats : {quantity} {quantity === 1 ? 'joueur' : 'joueurs'}
                </span>
            </div>
            {onShopping && (
                <div className="stadium-action-row">
                    <button
                        className="stadium-cta"
                        type="button"
                        aria-expanded={shoppingOpen}
                        aria-controls="report-shopping-content"
                        onClick={onShopping}
                    >
                        {shoppingOpen
                            ? 'Masquer les achats'
                            : quantity
                              ? 'Voir les achats'
                              : 'Voir les détails'}
                    </button>
                </div>
            )}
            <details className="squad-card-detail">
                <summary>Détails de la carte sélectionnée</summary>
                <p>
                    {selected.name} · {selected.rating} · {selected.position}
                </p>
                <p>
                    Version {candidate.card_id} · {credits(candidate.value)}
                </p>
            </details>
            <p className="squad-hero-caption">
                Coûts en crédits · Disposition illustrative · Aucune validation EA
            </p>
        </section>
    );
}
