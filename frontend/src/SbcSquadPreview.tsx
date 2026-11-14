import { useState } from 'react';
import { StadiumPitch, type PitchPlacement } from './design-a1/StadiumKit';
import type { SolverReport } from './lib/sbc-report';
import { credits } from './lib/sbc-report';
import portrait from './design-a1/assets/player-silhouette.svg';

// Disposition de lecture uniquement : ces positions ne sont jamais des coordonnées de clic.
const rows: Record<string, number> = {
    LW: 0,
    ST: 0,
    RW: 0,
    CF: 0,
    CAM: 1,
    CM: 1,
    CDM: 1,
    LM: 1,
    RM: 1,
    LB: 2,
    CB: 2,
    RB: 2,
    LWB: 2,
    RWB: 2,
    GK: 3,
};

export default function SbcSquadPreview({ report }: { report: SolverReport }) {
    const [chosen, setChosen] = useState<string | null>(null);
    const byKey = new Map(report.selected_candidates.map((card) => [card.key, card]));
    const assignments = report.solution.assignments ?? [];
    if (!assignments.length || assignments.length > 11 || report.challenge.mode === 'score')
        return null;
    const groups: Array<Array<{ slot: number; candidate_key: string }>> = [[], [], [], []];
    for (const assignment of assignments) {
        const position = report.challenge.positions?.[assignment.slot];
        if (!position || rows[position] === undefined || !byKey.has(assignment.candidate_key))
            return null;
        groups[rows[position]].push(assignment);
    }
    if (groups.some((group) => group.length > 5)) return null;
    const occupied = groups.filter((group) => group.length > 0);
    const compact = assignments.length <= 3 && occupied.length <= 2;
    const placements: PitchPlacement[] = groups.flatMap((group, row) =>
        group.map((assignment, index) => {
            const card = byKey.get(assignment.candidate_key)!;
            return {
                x:
                    group.length === 1
                        ? 50
                        : compact
                          ? 28 + (index * 44) / (group.length - 1)
                          : 15 + (index * 70) / (group.length - 1),
                y: compact
                    ? occupied.length === 1
                        ? 50
                        : 25 + occupied.indexOf(group) * 50
                    : 16 + row * 24,
                player: {
                    id: String(assignment.slot),
                    name: card.name,
                    position: report.challenge.positions![assignment.slot],
                    rating: card.rating,
                    origin: card.owned ? ('club' as const) : ('purchase' as const),
                    value: card.value ?? 0,
                },
            };
        }),
    );
    const selected =
        placements.find(({ player }) => player.id === chosen)?.player ?? placements[0].player;
    const candidate = byKey.get(
        assignments.find(({ slot }) => String(slot) === selected.id)!.candidate_key,
    )!;
    return (
        <section className="panel squad-visual-panel" aria-label="Aperçu de l’équipe du rapport">
            <div className="report-section-heading">
                <h3>Équipe proposée</h3>
                <span className="kind-label">{assignments.length} cartes</span>
            </div>
            <div className="stadium-squad-visual" data-small-squad={compact}>
                <StadiumPitch
                    placements={placements}
                    formation={`${assignments.length} cartes`}
                    selectedId={selected.id}
                    onSelect={setChosen}
                />
                <div className="stadium-selected" aria-live="polite">
                    <img src={portrait} alt="" />
                    <strong>
                        {selected.rating} · {selected.name} · {selected.position}
                    </strong>
                    <span
                        className={`stadium-origin ${selected.origin === 'purchase' ? 'stadium-origin-purchase' : ''}`}
                    >
                        {selected.origin === 'club' ? 'Club' : 'Achat'}
                    </span>
                </div>
                <p className="squad-card-detail">
                    Version {candidate.card_id} · {credits(candidate.value)}
                </p>
            </div>
            <p className="field-hint">
                Disposition illustrative. Les postes et les cartes viennent du rapport.
            </p>
        </section>
    );
}
