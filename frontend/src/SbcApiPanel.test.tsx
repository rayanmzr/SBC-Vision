// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import fixture from '../../data/fixtures/workspace-api.synthetic.json';
import SbcWorkspace from './SbcWorkspace';

const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });
afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
});
async function load() {
    fireEvent.click(screen.getByRole('button', { name: 'Charger l’inventaire' }));
    await screen.findByText('API de démonstration · Cartes fictives, calcul réel');
}
async function calculate() {
    fireEvent.click(screen.getByRole('button', { name: 'Calculer une proposition' }));
    await screen.findByText('API de démonstration · Calcul CP-SAT réel');
    fireEvent.click(screen.getByRole('button', { name: 'État et vérification du rapport' }));
    fireEvent.click(screen.getByRole('button', { name: 'Voir les achats' }));
    fireEvent.click(screen.getByRole('button', { name: 'Sources et inventaire' }));
}

it('vérifie la connexion puis affiche le résultat API et retire ce résultat si le budget change', async () => {
    const onConnect = vi.fn(async () => true);
    const fetchMock = vi.fn(async (url: string) =>
        json(url.endsWith('/solve') ? fixture.proposal : fixture.workspace),
    );
    vi.stubGlobal('fetch', fetchMock);
    render(<SbcWorkspace onConnect={onConnect} />);
    await load();
    expect(onConnect).toHaveBeenCalledOnce();
    await calculate();
    expect(
        screen.getByRole('heading', { name: 'Proposition optimale selon le rapport' }),
    ).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'Achats suggérés' })).toBeTruthy();
    fireEvent.change(
        screen.getByRole('spinbutton', { name: 'Budget d’achat pour le solveur API' }),
        { target: { value: '3000' } },
    );
    expect(screen.queryByRole('heading', { name: 'Achats suggérés' })).toBeNull();
    const next = structuredClone(fixture.proposal);
    next.report.challenge.budget = 3000;
    fetchMock.mockImplementation(async () => json(next));
    await calculate();
    const calls = fetchMock.mock.calls as unknown as Array<[string, RequestInit]>;
    expect(JSON.parse(String(calls.at(-1)![1].body)).budget).toBe(3000);
});

it('attend la confirmation du serveur avant de cocher la protection de la copie choisie', async () => {
    let finish!: (value: Response) => void;
    const pending = new Promise<Response>((resolve) => {
        finish = resolve;
    });
    vi.stubGlobal(
        'fetch',
        vi.fn(async (url: string) =>
            url.endsWith('/protections') ? pending : json(fixture.workspace),
        ),
    );
    render(<SbcWorkspace connected />);
    await load();
    const checkbox = screen.getByRole('checkbox', {
        name: 'Protection du serveur : club:demo-002',
    }) as HTMLInputElement;
    fireEvent.click(checkbox);
    expect(checkbox.checked).toBe(false);
    expect(checkbox.disabled).toBe(true);
    const updated = structuredClone(fixture.workspace);
    updated.revision = 'a'.repeat(64);
    updated.items[1].protected = true;
    await act(async () => finish(json(updated)));
    await screen.findByText('Protection enregistrée. Calculer une nouvelle proposition.');
    expect(checkbox.checked).toBe(true);
    expect(checkbox.disabled).toBe(false);
});

it('retire la proposition et impose une relecture si une protection échoue avec HTTP 409', async () => {
    vi.stubGlobal(
        'fetch',
        vi.fn(async (url: string) => {
            if (url.endsWith('/protections'))
                return json(
                    { detail: { code: 'workspace_changed', message: 'État modifié.' } },
                    409,
                );
            return json(url.endsWith('/solve') ? fixture.proposal : fixture.workspace);
        }),
    );
    render(<SbcWorkspace connected />);
    await load();
    await calculate();
    fireEvent.click(
        screen.getByRole('checkbox', { name: 'Protection du serveur : club:demo-002' }),
    );
    await screen.findByRole('alert');
    expect(screen.queryByRole('heading', { name: 'Achats suggérés' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Calculer une proposition' })).toBeNull();
    expect(screen.getByRole('alert').textContent).toContain('HTTP 409');
});

it('ignore un calcul tardif après le passage à un exemple fictif', async () => {
    let finish!: (value: Response) => void;
    const pending = new Promise<Response>((resolve) => {
        finish = resolve;
    });
    vi.stubGlobal(
        'fetch',
        vi.fn(async (url: string) => (url.endsWith('/solve') ? pending : json(fixture.workspace))),
    );
    render(<SbcWorkspace connected />);
    await load();
    fireEvent.click(screen.getByRole('button', { name: 'Calculer une proposition' }));
    fireEvent.click(screen.getByRole('button', { name: 'Exemple fictif' }));
    fireEvent.click(screen.getByRole('button', { name: 'Charger l’exemple du solveur →' }));
    await act(async () => finish(json(fixture.proposal)));
    expect(screen.getByText('Exemple synthétique · Aucun calcul exécuté')).toBeTruthy();
    expect(screen.queryByText('API de démonstration · Calcul CP-SAT réel')).toBeNull();
});

it('annule l’attente et ignore une réponse tardive sans annoncer une protection enregistrée', async () => {
    let finish!: (value: Response) => void;
    const pending = new Promise<Response>((resolve) => {
        finish = resolve;
    });
    vi.stubGlobal(
        'fetch',
        vi.fn(async (url: string) =>
            url.endsWith('/protections') ? pending : json(fixture.workspace),
        ),
    );
    render(<SbcWorkspace connected />);
    await load();
    fireEvent.click(
        screen.getByRole('checkbox', { name: 'Protection du serveur : club:demo-002' }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Annuler l’opération API' }));
    await act(async () => finish(json(fixture.workspace)));
    await waitFor(() =>
        expect(screen.getByRole('alert').textContent).toContain('Opération annulée'),
    );
    expect(
        screen.queryByText('Protection enregistrée. Calculer une nouvelle proposition.'),
    ).toBeNull();
    expect(screen.queryByRole('button', { name: 'Calculer une proposition' })).toBeNull();
});
