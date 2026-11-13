import { describe, expect, it } from 'vitest';
import fixture from '../../../data/fixtures/sbc-report.synthetic.json';
import { parseSolverReport, purchases, credits, readSolverFile } from './sbc-report';

describe('rapports du moteur SBC', () => {
    it('lit les cartes, les exemplaires, les prix inconnus et les achats', () => {
        const result = parseSolverReport(fixture);
        expect(result.kind).toBe('solver');
        if (result.kind !== 'solver') throw new Error();
        expect(result.report.selected_candidates.filter((card) => card.owned)).toHaveLength(2);
        expect(result.report.selected_candidates.some((card) => card.value == null)).toBe(true);
        expect(purchases(result.report).map((item) => item.card.name)).toEqual([
            'Eli Test',
            'Léa Fictive',
        ]);
        expect(credits(null)).toBe('Prix inconnu');
        expect(result.report.solution.purchase_cost).toBe(1300);
        expect(result.report.solution.total_cost).toBe(2100);
    });

    it.each([
        'missing-card',
        'wrong-cost',
        'unknown-price',
        'protected',
        'duplicate-slot',
        'duplicate-key',
        'quantity',
        'date',
        'contradictory-check',
    ])('refuse les données incohérentes : %s', (scenario) => {
        const data = structuredClone(fixture);
        if (scenario === 'missing-card') data.solution.assignments[0].candidate_key = 'missing';
        if (scenario === 'wrong-cost') data.solution.purchase_cost = 0;
        if (scenario === 'unknown-price') data.selected_candidates[2].value = null;
        if (scenario === 'protected') data.selected_candidates[1].protected = true;
        if (scenario === 'duplicate-slot') data.solution.assignments[1].slot = 0;
        if (scenario === 'duplicate-key')
            data.selected_candidates.push(data.selected_candidates[0]);
        if (scenario === 'quantity') data.selected_candidates[0].max_quantity = 2;
        if (scenario === 'date') data.price_reference_at = 'no-date';
        if (scenario === 'contradictory-check') data.verification.checks[0].passed = false;
        expect(() => parseSolverReport(data)).toThrow();
    });

    it.each(['infeasible', 'unknown'])(
        'accepte le statut %s sans le transformer en succès',
        (status) => {
            const data = {
                ...fixture,
                solution: {
                    status,
                    assignments: [],
                    purchase_cost: null,
                    sacrifice_value: null,
                    total_cost: null,
                },
                verification: null,
            };
            const result = parseSolverReport(data);
            expect(result.kind === 'solver' && result.report.solution.status).toBe(status);
            expect(() =>
                parseSolverReport({ ...data, solution: { ...fixture.solution, status } }),
            ).toThrow();
        },
    );

    it('bloque la composition si la lecture est incertaine, même avec un résultat résiduel', () => {
        expect(
            parseSolverReport({ ...fixture, ready: false, issues: ['Poste illisible'] }),
        ).toEqual({ kind: 'uncertain', issues: ['Poste illisible'] });
    });

    it('accepte un défi à score sans nouvel exemplaire', () => {
        const report = {
            ...fixture,
            challenge: {
                mode: 'score',
                market: 'pc',
                budget: 2000,
                positions: [],
                score_progress: 100,
                conditions: [{ metric: 'item_score', value: 100 }],
            },
            solution: {
                status: 'optimal',
                assignments: [],
                purchase_cost: 0,
                sacrifice_value: 0,
                total_cost: 0,
            },
            selected_candidates: [],
            verification: null,
        };
        expect(parseSolverReport(report)).toMatchObject({
            kind: 'solver',
            report: { solution: { total_cost: 0 } },
        });
    });

    it('importe un fichier local et refuse un JSON invalide ou trop volumineux', async () => {
        const file = new File([JSON.stringify(fixture)], 'solution.json', {
            type: 'application/json',
        });
        await expect(readSolverFile(file)).resolves.toMatchObject({ kind: 'solver' });
        await expect(readSolverFile(new File(['not JSON'], 'bad.json'))).rejects.toThrow('JSON');
        await expect(
            readSolverFile(new File([new Uint8Array(2 * 1024 * 1024 + 1)], 'huge.json')),
        ).rejects.toThrow('2 Mio');
    });
});
