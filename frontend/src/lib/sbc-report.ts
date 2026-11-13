import validateSchema from '../generated/sbc-report-validator.js';

export type Condition = {
    metric: string;
    op?: 'min' | 'max' | 'exact';
    value: number;
    target?: string | number | null;
    text?: string;
};
export type Candidate = {
    key: string;
    card_id: number;
    base_id: number;
    name: string;
    rating: number;
    positions: string[];
    owned: boolean;
    protected?: boolean;
    value?: number | null;
    max_quantity?: number;
    is_rare: boolean;
    observed_at: string;
    source_url: string;
};
export type SolverReport = {
    data_kind?: unknown;
    challenge: {
        mode?: 'squad' | 'score';
        positions?: string[];
        conditions?: Condition[];
        market: 'pc' | 'ps';
        budget: number;
        max_items?: number;
        max_card_value?: number | null;
    };
    price_reference_at: string;
    solution: {
        status: 'optimal' | 'feasible' | 'infeasible' | 'unknown';
        assignments?: Array<{ slot: number; candidate_key: string }>;
        purchase_cost?: number | null;
        sacrifice_value?: number | null;
        total_cost?: number | null;
        errors?: string[];
    };
    selected_candidates: Candidate[];
    verification?: {
        valid: boolean;
        checks: Array<
            Omit<Condition, 'value'> & {
                value: number | string;
                actual: number | number[] | Record<string, number> | null;
                passed: boolean;
            }
        >;
    } | null;
};

export function isSyntheticReport(report: SolverReport): boolean {
    return (
        report.data_kind === 'synthetic' ||
        (report.selected_candidates.length > 0 &&
            report.selected_candidates.every((card) =>
                card.source_url.startsWith('urn:sbc-vision:synthetic:'),
            ))
    );
}
export type ImportedReport =
    { kind: 'solver'; report: SolverReport } | { kind: 'uncertain'; issues: string[] };

export function parseSolverReport(value: unknown): ImportedReport {
    const raw = value as Record<string, unknown> | null;
    // Un ancien résultat contenu dans un rapport OCR incertain ne doit jamais être présenté.
    if (
        raw &&
        raw.ready === false &&
        Array.isArray(raw.issues) &&
        raw.issues.length > 0 &&
        raw.issues.length <= 200 &&
        raw.issues.every((issue) => typeof issue === 'string' && issue.length <= 2000)
    ) {
        return { kind: 'uncertain', issues: raw.issues as string[] };
    }
    if (!validateSchema(value))
        throw new Error(
            'Rapport de résolution attendu : challenge, solution, selected_candidates et price_reference_at.',
        );
    const report = value as SolverReport;
    if (!Number.isFinite(Date.parse(report.price_reference_at)))
        throw new Error('La date de référence des prix est invalide.');
    const byKey = new Map<string, Candidate>();
    for (const candidate of report.selected_candidates) {
        if (byKey.has(candidate.key))
            throw new Error('Le rapport contient des identifiants de cartes dupliqués.');
        if (candidate.owned && (candidate.max_quantity ?? 1) !== 1)
            throw new Error('Un exemplaire du club ne peut pas avoir plusieurs unités.');
        if (
            candidate.value != null &&
            (!Number.isSafeInteger(candidate.value) || candidate.value <= 0)
        )
            throw new Error('Une valeur de carte est invalide.');
        byKey.set(candidate.key, candidate);
    }
    const solution = report.solution;
    const assignments = solution.assignments ?? [];
    const successful = ['optimal', 'feasible'].includes(solution.status);
    if (!successful) {
        if (
            assignments.length ||
            [solution.purchase_cost, solution.sacrifice_value, solution.total_cost].some(
                (cost) => cost != null,
            )
        ) {
            throw new Error(
                'Un résultat sans solution ne doit pas contenir une ancienne composition ou des coûts.',
            );
        }
        return { kind: 'solver', report };
    }
    const squad = (report.challenge.mode ?? 'squad') === 'squad';
    if (
        squad &&
        (!(report.challenge.positions ?? []).length ||
            assignments.length !== (report.challenge.positions ?? []).length)
    ) {
        throw new Error('La composition ne couvre pas les emplacements du défi.');
    }
    const slots = new Set<number>(),
        quantities = new Map<string, number>();
    let purchase = 0,
        sacrifice = 0;
    for (const assignment of assignments) {
        const card = byKey.get(assignment.candidate_key);
        const limit = squad
            ? (report.challenge.positions ?? []).length
            : (report.challenge.max_items ?? 100);
        if (slots.has(assignment.slot) || assignment.slot >= limit)
            throw new Error('Un emplacement est dupliqué ou hors du défi.');
        slots.add(assignment.slot);
        if (!card) throw new Error('Une carte affectée est absente du rapport.');
        if (card.protected || card.value == null)
            throw new Error('Une carte affectée est protégée ou son prix est inconnu.');
        if (squad && !card.positions.includes(report.challenge.positions![assignment.slot]))
            throw new Error('Une carte ne correspond pas au poste annoncé.');
        if (report.challenge.max_card_value != null && card.value > report.challenge.max_card_value)
            throw new Error('Une carte dépasse le plafond de valeur du rapport.');
        const quantity = (quantities.get(card.key) ?? 0) + 1;
        if (quantity > (card.max_quantity ?? 1))
            throw new Error('Une carte est utilisée au-delà de sa quantité disponible.');
        quantities.set(card.key, quantity);
        if (card.owned) sacrifice += card.value;
        else purchase += card.value;
    }
    if (
        purchase !== solution.purchase_cost ||
        sacrifice !== solution.sacrifice_value ||
        purchase + sacrifice !== solution.total_cost ||
        !Number.isSafeInteger(purchase + sacrifice)
    ) {
        throw new Error('Les coûts annoncés ne correspondent pas aux cartes affectées.');
    }
    if (purchase > report.challenge.budget)
        throw new Error('Les achats dépassent le budget du rapport.');
    if (report.verification?.valid && report.verification.checks.some((check) => !check.passed)) {
        throw new Error('La vérification du rapport contient des résultats contradictoires.');
    }
    return { kind: 'solver', report };
}

export async function readSolverFile(file: File): Promise<ImportedReport> {
    if (!file.size || file.size > 2 * 1024 * 1024)
        throw new Error('Choisis un rapport JSON non vide de 2 Mio maximum.');
    let value: unknown;
    try {
        value = JSON.parse(await file.text());
    } catch {
        throw new Error('Le fichier ne contient pas de JSON lisible.');
    }
    return parseSolverReport(value);
}

export function purchases(report: SolverReport) {
    const byKey = new Map(report.selected_candidates.map((card) => [card.key, card]));
    const items = new Map<string, { card: Candidate; quantity: number }>();
    for (const assignment of report.solution.assignments ?? []) {
        const card = byKey.get(assignment.candidate_key)!;
        if (!card.owned)
            items.set(card.key, { card, quantity: (items.get(card.key)?.quantity ?? 0) + 1 });
    }
    return [...items.values()];
}

export function credits(value: number | null | undefined): string {
    return value == null ? 'Prix inconnu' : `${value.toLocaleString('fr-FR')} crédits`;
}

export function conditionLabel(condition: Condition): string {
    if (condition.text) return condition.text;
    const labels: Record<string, string> = {
        players: 'Joueurs',
        rating: 'Note individuelle',
        rated: 'Joueurs avec une note cible',
        rare: 'Joueurs rares',
        nation: 'Nationalité',
        league: 'Championnat',
        club: 'Club',
        nations: 'Nationalités différentes',
        leagues: 'Championnats différents',
        clubs: 'Clubs différents',
        same_nation: 'Même nationalité',
        same_league: 'Même championnat',
        same_club: 'Même club',
        quality: 'Qualité des cartes',
        item_score: 'Item Score',
        team_rating: 'Note d’équipe',
        chemistry: 'Collectif',
    };
    const operator = { min: '≥', max: '≤', exact: '=' }[condition.op ?? 'min'];
    return `${labels[condition.metric] ?? condition.metric}${condition.target != null ? ` (${condition.target})` : ''} ${operator} ${condition.value}`;
}
