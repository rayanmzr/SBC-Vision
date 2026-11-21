import validateWorkspace from '../generated/workspace-validator.js';
import validateSolveResponse from '../generated/solve-response-validator.js';
import { ApiError, requestJson } from './api';
import { parseSolverReport, type Candidate, type SolverReport } from './sbc-report';

export type Workspace = {
    mode: 'demo' | 'local';
    revision: string;
    price_reference_at: string;
    items: Candidate[];
    challenge: SolverReport['challenge'] | null;
    challenge_issues: string[];
};
export type PlacementCard = {
    slot: number;
    candidate_key: string;
    card_id: number;
    reading: {
        name: string;
        rating: number;
        position: string;
        stats: Record<string, number>;
        nation_id: number;
        league_id: number;
        club_id: number;
    };
};
export type PlacementPlan = { cards: PlacementCard[]; issues: string[] };
export type ApiProposal = {
    mode: 'demo' | 'local';
    revision: string;
    report: SolverReport;
    placement?: PlacementPlan | null;
};

// L'ordre des clés JSON peut varier entre la capture et la réponse Python.
function ordered(value: unknown): unknown {
    if (Array.isArray(value)) return value.map(ordered);
    if (value && typeof value === 'object')
        return Object.fromEntries(
            Object.entries(value)
                .sort()
                .map(([k, v]) => [k, ordered(v)]),
        );
    return value;
}

export function parseWorkspace(value: unknown): Workspace {
    if (!validateWorkspace(value))
        throw new ApiError('L’inventaire reçu ne respecte pas le contrat API.', 'invalid_response');
    const workspace = value as Workspace;
    if (
        !/^[0-9a-f]{64}$/.test(workspace.revision) ||
        !Number.isFinite(Date.parse(workspace.price_reference_at)) ||
        new Set(workspace.items.map((card) => card.key)).size !== workspace.items.length ||
        workspace.items.some(
            (card) => !card.owned || !card.key.startsWith('club:') || card.key.length <= 5,
        )
    ) {
        throw new ApiError(
            'L’inventaire reçu contient une révision ou des exemplaires incohérents.',
            'invalid_response',
        );
    }
    return workspace;
}

export async function loadWorkspace(base: string, signal: AbortSignal): Promise<Workspace> {
    return parseWorkspace(await requestJson(base, '/api/v1/sbc/workspace', {}, signal, 10_000));
}

export async function updateProtection(
    base: string,
    workspace: Workspace,
    key: string,
    protectedValue: boolean,
    signal: AbortSignal,
): Promise<Workspace> {
    const card = workspace.items.find((item) => item.key === key);
    if (!card?.owned || !key.startsWith('club:'))
        throw new ApiError('Exemplaire absent de l’inventaire affiché.', 'invalid_item');
    const response = await requestJson(
        base,
        '/api/v1/sbc/protections',
        {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                instance_id: key.slice(5),
                protected: protectedValue,
                expected_revision: workspace.revision,
            }),
        },
        signal,
        10_000,
    );
    const updated = parseWorkspace(response);
    if (updated.mode !== workspace.mode)
        throw new ApiError('Le mode du serveur a changé. Recharger l’espace.', 'workspace_changed');
    if (!updated.items.some((item) => item.key === key && item.protected === protectedValue)) {
        throw new ApiError(
            'L’état de cette protection ne peut pas être confirmé. Recharger l’inventaire.',
            'workspace_changed',
        );
    }
    return updated;
}

export async function solveWorkspace(
    base: string,
    workspace: Workspace,
    budget: number,
    signal: AbortSignal,
): Promise<ApiProposal> {
    if (
        !workspace.challenge ||
        !Number.isSafeInteger(budget) ||
        budget < 0 ||
        budget > 1_000_000_000
    ) {
        throw new ApiError(
            'Fournir des conditions confirmées et un budget entier positif ou nul.',
            'invalid_input',
        );
    }
    const value = await requestJson(
        base,
        '/api/v1/sbc/solve',
        {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                expected_revision: workspace.revision,
                budget,
                challenge: workspace.challenge,
            }),
        },
        signal,
        30_000,
    );
    if (!validateSolveResponse(value))
        throw new ApiError(
            'La réponse du solveur ne respecte pas le contrat API.',
            'invalid_response',
        );
    const response = value as ApiProposal;
    if (response.revision !== workspace.revision || response.mode !== workspace.mode)
        throw new ApiError(
            'La proposition correspond à un autre état de l’inventaire.',
            'workspace_changed',
        );
    const parsed = parseSolverReport(response.report);
    if (
        parsed.kind !== 'solver' ||
        JSON.stringify(ordered(parsed.report.challenge)) !==
            JSON.stringify(ordered({ ...workspace.challenge, budget })) ||
        parsed.report.data_kind !== (response.mode === 'demo' ? 'synthetic' : 'local')
    ) {
        throw new ApiError(
            'Les conditions ou la provenance de la proposition ne correspondent pas à la demande.',
            'invalid_response',
        );
    }
    return { ...response, report: parsed.report };
}
