// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import fixture from '../../data/fixtures/sbc-report.synthetic.json';
import SbcWorkspace from './SbcWorkspace';

afterEach(cleanup);

it('garde la mention fictive et les protections en lecture seule pour un fichier importé', async () => {
    render(<SbcWorkspace />);
    const file = new File(['test report'], 'solution.json', { type: 'application/json' });
    Object.defineProperty(file, 'text', { value: async () => JSON.stringify(fixture) });
    fireEvent.change(screen.getByLabelText('Importer un rapport SBC JSON'), {
        target: { files: [file] },
    });
    await screen.findByText('Rapport importé · Données fictives');
    expect(
        (
            screen.getByRole('checkbox', {
                name: 'Protéger Alex Exemple club:demo-002',
            }) as HTMLInputElement
        ).disabled,
    ).toBe(true);
});

function loadExample() {
    render(<SbcWorkspace />);
    fireEvent.click(screen.getByRole('button', { name: 'Charger l’exemple du solveur →' }));
}

it('distingue dépenses, valeur sacrifiée, protections et prix inconnu', () => {
    loadExample();
    expect(screen.getByText('Exemple synthétique · Aucun calcul exécuté')).toBeTruthy();
    expect(screen.getByText('Proposition optimale selon le rapport')).toBeTruthy();
    expect(screen.getByText('Prix inconnu')).toBeTruthy();
    expect(
        (
            screen.getByRole('checkbox', {
                name: 'Protéger Alex Exemple club:demo-001',
            }) as HTMLInputElement
        ).checked,
    ).toBe(true);
    expect(screen.getByRole('heading', { name: 'Achats suggérés' })).toBeTruthy();
});

it('retire la composition et les coûts après une modification locale de protection', () => {
    loadExample();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Protéger Alex Exemple club:demo-002' }));
    expect(screen.getByText('Recalcul nécessaire')).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'Achats suggérés' })).toBeNull();
    expect(screen.getByText('Proposition à recalculer.')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Charger l’exemple du solveur →' }));
    expect(screen.getByText('Proposition optimale selon le rapport')).toBeTruthy();
});

it.each([
    ['infeasible', 'Aucune solution sur le pool connu'],
    ['unknown', 'Recherche sans conclusion'],
    ['uncertain', 'Lecture à confirmer'],
])('présente correctement le cas %s', (scenario, message) => {
    loadExample();
    fireEvent.change(screen.getByRole('combobox', { name: 'Scénario du solveur' }), {
        target: { value: scenario },
    });
    expect(screen.getByRole('heading', { name: message })).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'Achats suggérés' })).toBeNull();
});
