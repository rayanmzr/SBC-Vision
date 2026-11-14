// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import fixture from '../../data/fixtures/sbc-report.synthetic.json';
import type { SolverReport } from './lib/sbc-report';
import SbcSquadPreview from './SbcSquadPreview';

afterEach(cleanup);

it('montre les trois cartes retenues et les détails de la carte sélectionnée', () => {
    render(<SbcSquadPreview report={structuredClone(fixture) as SolverReport} />);
    expect(screen.getAllByRole('button')).toHaveLength(3);
    expect(screen.getAllByRole('button', { name: /Alex Exemple/ })).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: 'Léa Fictive, 83, ST, Achat' }));
    expect(screen.getByText(/Version 900004/).textContent).toContain('400 crédits');
    expect(
        screen
            .getByRole('button', { name: 'Léa Fictive, 83, ST, Achat' })
            .getAttribute('aria-pressed'),
    ).toBe('true');
    expect(screen.getByRole('region', { name: 'Composition 3 cartes' })).toBeTruthy();
});

it.each(['score', 'unknown-position', 'prototype-position'])(
    'n’invente pas de terrain pour un rapport %s',
    (mode) => {
        const report = structuredClone(fixture) as SolverReport;
        if (mode === 'score') report.challenge.mode = 'score';
        else
            report.challenge.positions![0] = mode === 'prototype-position' ? 'toString' : 'UNKNOWN';
        const { container } = render(<SbcSquadPreview report={report} />);
        expect(container.childElementCount).toBe(0);
    },
);
