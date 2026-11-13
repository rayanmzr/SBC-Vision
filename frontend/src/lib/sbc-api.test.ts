import { afterEach, describe, expect, it, vi } from 'vitest';
import fixture from '../../../data/fixtures/workspace-api.synthetic.json';
import { DEFAULT_API_URL } from './platform';
import { loadWorkspace, parseWorkspace, solveWorkspace, updateProtection } from './sbc-api';
import { parseSolverReport } from './sbc-report';

const signal = () => new AbortController().signal;
const workspace = () => parseWorkspace(structuredClone(fixture.workspace));
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });
afterEach(() => vi.unstubAllGlobals());

describe('inventaire du serveur', () => {
    it('charge les exemplaires du club, y compris les deux copies de la même version', async () => {
        const fetchMock = vi.fn(async () => json(fixture.workspace));
        vi.stubGlobal('fetch', fetchMock);
        const state = await loadWorkspace(DEFAULT_API_URL, signal());
        expect(state.items).toHaveLength(3);
        expect(state.items[0].card_id).toBe(state.items[1].card_id);
        expect(state.items[0].key).not.toBe(state.items[1].key);
        expect(fetchMock.mock.calls[0]).toEqual([
            expect.stringContaining('/api/v1/sbc/workspace'),
            expect.objectContaining({ credentials: 'omit', redirect: 'error' }),
        ]);
    });

    it.each(['revision', 'duplicate', 'market', 'key', 'date'])(
        'refuse un inventaire incohérent : %s',
        (fault) => {
            const state = structuredClone(fixture.workspace);
            if (fault === 'revision') state.revision = 'old';
            if (fault === 'duplicate') state.items.push(state.items[0]);
            if (fault === 'market') state.items[0].owned = false;
            if (fault === 'key') state.items[0].key = 'market:900001';
            if (fault === 'date') state.price_reference_at = 'yesterday';
            expect(() => parseWorkspace(state)).toThrow();
        },
    );

    it('enregistre une copie précise avec la révision affichée et vérifie la confirmation', async () => {
        const updated = workspace();
        updated.items[1].protected = true;
        updated.revision = 'a'.repeat(64);
        const fetchMock = vi.fn(async () => json(updated));
        vi.stubGlobal('fetch', fetchMock);
        const result = await updateProtection(
            DEFAULT_API_URL,
            workspace(),
            'club:demo-002',
            true,
            signal(),
        );
        expect(result.items[1].protected).toBe(true);
        const [, options] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
        expect(options.method).toBe('PUT');
        expect(options.headers).toEqual({ 'Content-Type': 'application/json' });
        expect(JSON.parse(String(options.body))).toEqual({
            instance_id: 'demo-002',
            protected: true,
            expected_revision: fixture.workspace.revision,
        });
    });

    it('refuse une protection non confirmée et conserve une erreur de révision HTTP 409', async () => {
        vi.stubGlobal(
            'fetch',
            vi.fn(async () => json(fixture.workspace)),
        );
        await expect(
            updateProtection(DEFAULT_API_URL, workspace(), 'club:demo-002', true, signal()),
        ).rejects.toMatchObject({ code: 'workspace_changed' });
        vi.stubGlobal(
            'fetch',
            vi.fn(async () =>
                json(
                    {
                        detail: {
                            code: 'workspace_changed',
                            message: 'État modifié.',
                        },
                    },
                    409,
                ),
            ),
        );
        await expect(
            updateProtection(DEFAULT_API_URL, workspace(), 'club:demo-002', true, signal()),
        ).rejects.toMatchObject({ code: 'workspace_changed', status: 409 });
    });
});

describe('proposition du véritable solveur', () => {
    it('accepte les notes individuelles et le décompte de qualités du vérificateur Python', () => {
        const report = structuredClone(fixture.proposal.report);
        const qualityCheck = {
            metric: 'card_level',
            op: 'exact',
            value: 'GOLD',
            actual: { GOLD: 3 },
            passed: true,
        };
        const verified = {
            ...report,
            verification: {
                valid: true,
                checks: [...report.verification.checks, qualityCheck],
            },
        };
        expect(parseSolverReport(verified).kind).toBe('solver');
        qualityCheck.actual = { GOLD: -1 };
        expect(() => parseSolverReport(verified)).toThrow();
    });

    it('envoie seulement le budget et la révision en JSON et lit le calcul de la fixture', async () => {
        const fetchMock = vi.fn(async () => json(fixture.proposal));
        vi.stubGlobal('fetch', fetchMock);
        const proposal = await solveWorkspace(DEFAULT_API_URL, workspace(), 2000, signal());
        expect(proposal.report.solution).toMatchObject({
            status: 'optimal',
            purchase_cost: 1300,
            sacrifice_value: 800,
            total_cost: 2100,
        });
        const [url, options] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
        expect(url).toContain('/api/v1/sbc/solve');
        expect(options.method).toBe('POST');
        expect(options.headers).toEqual({ 'Content-Type': 'application/json' });
        expect(JSON.parse(String(options.body))).toEqual({
            expected_revision: fixture.workspace.revision,
            budget: 2000,
        });
    });

    it.each(['revision', 'mode', 'budget', 'provenance'])(
        'refuse une réponse associée à un autre contexte : %s',
        async (fault) => {
            const proposal = structuredClone(fixture.proposal);
            if (fault === 'revision') proposal.revision = 'b'.repeat(64);
            if (fault === 'mode') proposal.mode = 'local';
            if (fault === 'budget') proposal.report.challenge.budget = 9999;
            if (fault === 'provenance') proposal.report.data_kind = 'local';
            vi.stubGlobal(
                'fetch',
                vi.fn(async () => json(proposal)),
            );
            await expect(
                solveWorkspace(DEFAULT_API_URL, workspace(), 2000, signal()),
            ).rejects.toThrow();
        },
    );

    it('ne lance aucun calcul sans conditions confirmées ou avec un budget invalide', async () => {
        const fetchMock = vi.fn();
        vi.stubGlobal('fetch', fetchMock);
        await expect(
            solveWorkspace(DEFAULT_API_URL, { ...workspace(), challenge: null }, 2000, signal()),
        ).rejects.toThrow();
        await expect(solveWorkspace(DEFAULT_API_URL, workspace(), -1, signal())).rejects.toThrow();
        expect(fetchMock).not.toHaveBeenCalled();
    });
});
