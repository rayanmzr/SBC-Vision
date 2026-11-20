// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import fixture from '../../data/fixtures/sbc-report.synthetic.json';
import SbcWorkspace from './SbcWorkspace';

afterEach(cleanup);

it('garde la mention fictive et les protections en lecture seule pour un fichier importé', async () => {
    render(<SbcWorkspace />);
    fireEvent.click(screen.getByRole('button', { name: 'Rapport local' }));
    const file = new File(['test report'], 'solution.json', { type: 'application/json' });
    Object.defineProperty(file, 'text', { value: async () => JSON.stringify(fixture) });
    fireEvent.change(screen.getByLabelText('Importer un rapport SBC JSON'), {
        target: { files: [file] },
    });
    await screen.findByText('Rapport importé · Données fictives');
    fireEvent.click(screen.getByRole('button', { name: 'Cartes et protections' }));
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
    fireEvent.click(screen.getByRole('button', { name: 'Exemple fictif' }));
    fireEvent.click(screen.getByRole('button', { name: 'Charger l’exemple du solveur →' }));
    fireEvent.click(screen.getByRole('button', { name: 'Cartes et protections' }));
    fireEvent.click(screen.getByRole('button', { name: 'Voir les achats' }));
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
    fireEvent.click(screen.getByRole('button', { name: 'Sources et inventaire' }));
    fireEvent.change(screen.getByRole('combobox', { name: 'Scénario du solveur' }), {
        target: { value: scenario },
    });
    expect(screen.getByRole('heading', { name: message })).toBeTruthy();
    expect(screen.getByText('Exemple synthétique · Aucun calcul exécuté')).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'Achats suggérés' })).toBeNull();
    expect(screen.queryByLabelText('Coûts du rapport')).toBeNull();
});

it('place l’équipe et les coûts au premier plan et déplie les achats sur demande', () => {
    render(<SbcWorkspace />);
    fireEvent.click(screen.getByRole('button', { name: 'Exemple fictif' }));
    fireEvent.click(screen.getByRole('button', { name: 'Charger l’exemple du solveur →' }));
    expect(screen.getByRole('region', { name: 'Aperçu de l’équipe du rapport' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Charger l’inventaire' })).toBeNull();
    expect(screen.queryByRole('heading', { name: 'Achats suggérés' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Voir les achats' }));
    expect(screen.getByRole('heading', { name: 'Achats suggérés' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Masquer les achats' }));
    expect(screen.queryByRole('heading', { name: 'Achats suggérés' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Cartes et protections' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Protéger Alex Exemple club:demo-002' }));
    expect(screen.queryByRole('region', { name: 'Aperçu de l’équipe du rapport' })).toBeNull();
    expect(screen.getByText('Recalcul nécessaire')).toBeTruthy();
});

it('présente onze cartes fictives avec des coûts cohérents et une formation issue des postes', () => {
    render(<SbcWorkspace />);
    fireEvent.click(screen.getByRole('button', { name: 'Exemple fictif' }));
    fireEvent.change(screen.getByRole('combobox', { name: 'Scénario du solveur' }), {
        target: { value: 'eleven' },
    });
    expect(screen.getByRole('region', { name: 'Composition 4-3-3' })).toBeTruthy();
    expect(screen.getAllByRole('button', { name: /, (Club|Achat)$/ })).toHaveLength(11);
    expect(screen.getByText(/11\s000/)).toBeTruthy();
    expect(screen.getByText('Exemple synthétique · Aucun calcul exécuté')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Voir les achats' }));
    expect(screen.getByText(/Total : 1\s700 crédits/)).toBeTruthy();
    expect(screen.getByText(/Total : 2\s500 crédits/)).toBeTruthy();
});
