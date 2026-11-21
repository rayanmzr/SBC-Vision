import type { SolverReport } from './sbc-report';
import type { PitchPlacement } from '../design-a1/StadiumKit';

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

// Présentation du rapport uniquement ; aucun lien avec les coordonnées du contrôleur.
export function squadLayout(report: SolverReport) {
    const byKey = new Map(report.selected_candidates.map((card) => [card.key, card]));
    const assignments = report.solution.assignments ?? [];
    if (
        !['optimal', 'feasible'].includes(report.solution.status) ||
        !assignments.length ||
        assignments.length > 11 ||
        report.challenge.mode === 'score'
    )
        return null;
    const groups: Array<typeof assignments> = [[], [], [], []];
    for (const assignment of assignments) {
        const position = report.challenge.positions?.[assignment.slot];
        if (!position || !Object.hasOwn(rows, position) || !byKey.has(assignment.candidate_key))
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
                          : group.length === 3
                            ? 27 + index * 23
                            : group.length === 2
                              ? 32 + index * 36
                              : 15 + (index * 70) / (group.length - 1),
                y: compact
                    ? occupied.length === 1
                        ? 50
                        : 25 + occupied.indexOf(group) * 50
                    : [18, 43, 68, 89.5][row],
                player: {
                    id: String(assignment.slot),
                    name: card.name,
                    position: report.challenge.positions![assignment.slot],
                    rating: card.rating,
                    origin: card.owned ? 'club' : 'purchase',
                    value: card.value ?? 0,
                },
            };
        }),
    );
    const formation =
        assignments.length === 11 && groups[3].length === 1
            ? groups
                  .slice(0, 3)
                  .reverse()
                  .map((group) => group.length)
                  .join('-')
            : `${assignments.length} cartes`;
    return { placements, compact, formation };
}
