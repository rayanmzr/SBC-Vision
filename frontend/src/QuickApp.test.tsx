// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import App from './App';
import fixture from '../../data/fixtures/workspace-api.synthetic.json';
import { scanClub, prepareSbc } from './lib/club-scan';
import { fillSbc, type PreparedSbc } from './lib/sbc-fill';
import { updateProtection } from './lib/sbc-api';

vi.mock('./lib/club-scan', () => ({ scanClub: vi.fn(), prepareSbc: vi.fn() }));
vi.mock('./lib/sbc-fill', () => ({ fillSbc: vi.fn() }));
vi.mock('./lib/sbc-api', async (original) => ({
    ...(await original<typeof import('./lib/sbc-api')>()),
    updateProtection: vi.fn(),
}));
vi.mock('./lib/platform', async (original) => ({
    ...(await original<typeof import('./lib/platform')>()),
    loadApiUrl: vi.fn(async () => 'http://127.0.0.1:8000'),
    authorizeApi: vi.fn(async () => {}),
    saveApiUrl: vi.fn(async () => {}),
}));
beforeEach(() => {
    vi.mocked(scanClub)
        .mockReset()
        .mockResolvedValue({ capture_id: 'synthetic-scan', pages: [], complete: true });
    vi.mocked(prepareSbc)
        .mockReset()
        .mockResolvedValue({
            ...fixture.proposal,
            context: {},
            board: {},
        } as unknown as PreparedSbc);
    vi.mocked(fillSbc).mockReset().mockResolvedValue(3);
    vi.mocked(updateProtection)
        .mockReset()
        .mockResolvedValue({ ...fixture.workspace, mode: 'local' } as Awaited<
            ReturnType<typeof updateProtection>
        >);
    vi.stubGlobal(
        'fetch',
        vi.fn(
            async (url: string, options?: RequestInit) =>
                new Response(
                    JSON.stringify(
                        url.endsWith('/health')
                            ? { status: 'ok', version: '0.1.0', model_loaded: true }
                            : url.endsWith('/capabilities')
                              ? { perception: true, ocr: true }
                              : url.endsWith('/workspace')
                                ? { ...fixture.workspace, mode: 'local' }
                                : {
                                      observed: 20,
                                      identified: 10,
                                      pending: 10,
                                      loans: 2,
                                      complete: true,
                                      expected_revision: fixture.workspace.revision,
                                      inventory_updated: options?.body
                                          ? JSON.parse(String(options.body)).confirmed
                                          : false,
                                  },
                    ),
                ),
        ),
    );
});
afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
});

it('affiche seulement les deux actions principales, avec les réglages repliés', async () => {
    render(<App />);
    expect(await screen.findByRole('button', { name: 'Scanner mon club' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Compléter ce SBC' })).toBeTruthy();
    expect(document.querySelectorAll('.quick-actions button')).toHaveLength(2);
    expect((document.querySelector('.quick-options') as HTMLDetailsElement).open).toBe(false);
    expect(fetch).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: 'Envoyer à l’API' })).toBeNull();
});

it('un clic scanne puis enregistre le club identifié sous protection sans toucher à EA', async () => {
    render(<App />);
    const scan = await screen.findByRole('button', { name: 'Scanner mon club' });
    await vi.waitFor(() => expect((scan as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(scan);
    await screen.findByText(
        '20 cartes enregistrées ; 10 identifiées et protégées. 10 restent à vérifier.',
    );
    const calls = vi.mocked(fetch).mock.calls.filter(([u]) => String(u).endsWith('/club-scan'));
    expect(calls).toHaveLength(2);
    expect(JSON.parse(String(calls[0][1]?.body)).confirmed).toBe(false);
    expect(JSON.parse(String(calls[1][1]?.body)).confirmed).toBe(true);
    expect(prepareSbc).not.toHaveBeenCalled();
});

it('raccorde la préparation au placement sans bouton de soumission', async () => {
    render(<App />);
    const button = await screen.findByRole('button', { name: 'Compléter ce SBC' });
    await vi.waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(button);
    await screen.findByText('Composition proposée');
    expect(prepareSbc).toHaveBeenCalled();
    await screen.findByText(/3 joueurs placés/);
    expect(fillSbc).toHaveBeenCalledOnce();
    expect(screen.queryByRole('button', { name: /valider|submit|exchange/i })).toBeNull();
    expect(scanClub).not.toHaveBeenCalled();
});

it('ne présente jamais un calcul impossible comme une proposition prête', async () => {
    vi.mocked(prepareSbc).mockResolvedValue({
        ...fixture.proposal,
        context: {},
        board: {},
        report: { ...fixture.proposal.report, solution: { status: 'infeasible', assignments: [] } },
    } as unknown as PreparedSbc);
    render(<App />);
    const button = await screen.findByRole('button', { name: 'Compléter ce SBC' });
    await vi.waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(button);
    await screen.findByText('Aucune composition disponible');
    expect(screen.getByText(/Aucune équipe trouvée dans le catalogue actuel/)).toBeTruthy();
    expect(screen.queryByText(/Prix inconnu/)).toBeNull();
    expect(screen.queryByText(/Proposition prête/)).toBeNull();
    expect(fillSbc).not.toHaveBeenCalled();
});

it('explique que toutes les cartes protégées sont exclues du calcul', async () => {
    vi.mocked(prepareSbc).mockResolvedValue({
        ...fixture.proposal,
        report: { ...fixture.proposal.report, solution: { status: 'infeasible', assignments: [] } },
    } as unknown as PreparedSbc);
    vi.mocked(fetch).mockImplementation(
        async (url) =>
            new Response(
                JSON.stringify(
                    String(url).endsWith('/health')
                        ? { status: 'ok', version: '0.1.0', model_loaded: true }
                        : String(url).endsWith('/capabilities')
                          ? { perception: true, ocr: true }
                          : {
                                ...fixture.workspace,
                                mode: 'local',
                                items: fixture.workspace.items.map((c) => ({
                                    ...c,
                                    protected: true,
                                })),
                            },
                ),
            ),
    );
    render(<App />);
    const button = await screen.findByRole('button', { name: 'Compléter ce SBC' });
    await vi.waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(button);
    await screen.findByText(/Tes 3 cartes sont protégées/);
    expect(fillSbc).not.toHaveBeenCalled();
    expect(screen.queryByText(/Prix inconnu/)).toBeNull();
});

it('autorise explicitement les cartes de base protégées sous le plafond sur une action explicite', async () => {
    const items = fixture.workspace.items.map((c) => ({ ...c, chemistry_kind: 'standard' }));
    items[2].value = 500;
    items[2].protected = true;
    items.push({ ...items[0], key: 'club:unsupported', chemistry_kind: 'unsupported' });
    items.push({ ...items[0], key: 'club:expensive', value: 1001 });
    vi.mocked(fetch).mockImplementation(
        async (url) =>
            new Response(
                JSON.stringify(
                    String(url).endsWith('/health')
                        ? { status: 'ok', version: '0.1.0', model_loaded: true }
                        : String(url).endsWith('/capabilities')
                          ? { perception: true, ocr: true }
                          : { ...fixture.workspace, mode: 'local', items },
                ),
            ),
    );
    render(<App />);
    expect(updateProtection).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('Options', { exact: true }));
    const button = screen.getByRole('button', {
        name: 'Autoriser les cartes de base sous ce plafond',
    });
    await vi.waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(button);
    await screen.findByText(/cartes de base sous .* autorisées/);
    const eligible = items.filter(
        (c) => c.protected && c.chemistry_kind === 'standard' && c.value != null && c.value <= 1000,
    );
    expect(eligible.length).toBeGreaterThan(0);
    expect(eligible.some((c) => c.is_rare)).toBe(true);
    expect(vi.mocked(updateProtection).mock.calls.map((c) => c[2])).toEqual(
        eligible.map((c) => c.key),
    );
    expect(vi.mocked(updateProtection).mock.calls.every((c) => c[3] === false)).toBe(true);
    expect(scanClub).not.toHaveBeenCalled();
    expect(prepareSbc).not.toHaveBeenCalled();
    expect(fillSbc).not.toHaveBeenCalled();
});

it('conserve la proposition si un achat ou une vérification manuelle bloque le placement', async () => {
    vi.mocked(fillSbc).mockRejectedValue(new Error('À acheter manuellement : Exemple.'));
    render(<App />);
    const button = await screen.findByRole('button', { name: 'Compléter ce SBC' });
    await vi.waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(button);
    await screen.findByText('À acheter manuellement : Exemple.');
    expect(screen.getByText('Composition proposée')).toBeTruthy();
    expect(screen.queryByText(/joueurs placés/)).toBeNull();
});
