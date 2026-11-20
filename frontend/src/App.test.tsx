// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, act } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import fixture from '../../data/fixtures/perception.synthetic.json';
import sbcFixture from '../../data/fixtures/workspace-api.synthetic.json';
import App from './Diagnostics';
import { readImage } from './lib/api';
import { sessionApiHeaders } from './lib/api-key';

vi.mock('./lib/api', async (importOriginal) => ({
    ...(await importOriginal<typeof import('./lib/api')>()),
    readImage: vi.fn(async () => ({ url: 'blob:synthetic-test', width: 1280, height: 720 })),
}));

beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal(
        'fetch',
        vi.fn(
            async (url: string) =>
                new Response(
                    JSON.stringify(
                        url.endsWith('/health')
                            ? { status: 'ok', version: '0.1.0', model_loaded: false }
                            : url.endsWith('/capabilities')
                              ? { perception: false, ocr: false }
                              : {
                                    detail: {
                                        code: 'perception_unavailable',
                                        message: 'Pipeline absent.',
                                    },
                                },
                    ),
                    { status: url.includes('/analyze') ? 503 : 200 },
                ),
        ),
    );
    URL.revokeObjectURL = vi.fn();
});
afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
});

async function openSettings() {
    fireEvent.click(screen.getByRole('button', { name: 'Réglages' }));
    await waitFor(() =>
        expect(
            (screen.getByRole('button', { name: 'Vérifier la connexion' }) as HTMLButtonElement)
                .disabled,
        ).toBe(false),
    );
}
function openAnalysis() {
    fireEvent.click(screen.getByRole('button', { name: 'Analyser' }));
}
async function connectAndChoose() {
    await openSettings();
    fireEvent.click(screen.getByRole('button', { name: 'Vérifier la connexion' }));
    await screen.findByText('Serveur joignable · v0.1.0');
    openAnalysis();
    fireEvent.change(screen.getByLabelText('Choisir une image PNG ou JPEG'), {
        target: { files: [new File(['pixels'], 'capture.png', { type: 'image/png' })] },
    });
    await screen.findByText('capture.png');
}

it('attend le choix de version et transmet les conditions OCR au solveur', async () => {
    const challenge = { ...structuredClone(sbcFixture.workspace.challenge), budget: 4321 };
    const fetchMock = vi.fn(async (url: string) => {
        const captureId = new URL(url, 'http://localhost').searchParams.get('capture_id');
        const value = url.endsWith('/health')
            ? { status: 'ok', version: '0.1.0', model_loaded: true }
            : url.endsWith('/capabilities')
              ? { perception: true, ocr: true }
              : url.includes('/perception/analyze')
                ? {
                      ...fixture,
                      capture_id: captureId,
                      elements: [{ ...fixture.elements[0], id: 'card-1', kind: 'card' }],
                      ocr: {
                          capture_id: captureId,
                          image: fixture.image,
                          engine_version: 'synthetic-test',
                          language: 'eng',
                          automatic_detection: true,
                          region_source: 'detected',
                          minimum_confidence: 0.75,
                          regions: [],
                          positions: [],
                          cards: [
                              {
                                  element_id: 'card-1',
                                  candidate_ids: [900001, 900002],
                                  issues: [],
                                  needs_confirmation: true,
                                  reading: {
                                      capture_id: captureId,
                                      element_id: 'card-1',
                                      name: 'Alex Exemple',
                                      rating: 83,
                                      confidence: 0.99,
                                  },
                              },
                          ],
                          challenge_ready: true,
                          challenge,
                          challenge_issues: [],
                      },
                  }
                : sbcFixture.workspace;
        return new Response(JSON.stringify(value));
    });
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);
    await connectAndChoose();
    fireEvent.click(screen.getByRole('button', { name: /Envoyer à l’API/ }));
    await screen.findByText('Versions candidates : 900001, 900002', { exact: false });
    expect(fetchMock.mock.calls.some(([url]) => url.endsWith('/inventory'))).toBe(false);
    fireEvent.change(screen.getByLabelText('Alex Exemple : identifiant de l’exemplaire'), {
        target: { value: 'copy-1' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Confirmer l’ajout au club local' }));
    await screen.findByText('Choisir une version et un identifiant d’exemplaire.');
    expect(fetchMock.mock.calls.some(([url]) => url.endsWith('/inventory'))).toBe(false);
    fireEvent.change(screen.getByLabelText('Version vérifiée'), { target: { value: '900002' } });
    fireEvent.click(screen.getByRole('button', { name: 'Confirmer l’ajout au club local' }));
    await screen.findByText('Lectures enregistrées dans le club local, avec protection activée.');
    const [, options] = vi
        .mocked(fetch)
        .mock.calls.find(([url]) => String(url).endsWith('/inventory'))!;
    expect(JSON.parse(String(options?.body))).toMatchObject({
        expected_revision: sbcFixture.workspace.revision,
        confirmed: true,
        choices: { 'card-1': { instance_id: 'copy-1', card_id: 900002, protected: true } },
    });
    fireEvent.click(
        screen.getByRole('button', { name: 'Utiliser ces conditions dans le solveur' }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Charger l’inventaire' }));
    await screen.findByText('API de démonstration · Cartes fictives, calcul réel');
    expect(
        (screen.getByLabelText('Budget d’achat pour le solveur API') as HTMLInputElement).value,
    ).toBe('4321');
});

it('attend un geste utilisateur et présente explicitement la fixture', async () => {
    render(<App />);
    await openSettings();
    openAnalysis();
    expect(fetch).not.toHaveBeenCalled();
    expect(
        (screen.getByRole('button', { name: /Envoyer à l’API/ }) as HTMLButtonElement).disabled,
    ).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: /Voir un exemple synthétique/ }));
    expect(screen.getByText('Exemple synthétique · Données fictives')).toBeTruthy();
    expect(screen.getByText('2 éléments')).toBeTruthy();
    expect(screen.getByText('Source : synthetic-fixture-no-inference')).toBeTruthy();
    expect(fetch).not.toHaveBeenCalled();
});

it('affiche la vraie erreur du pipeline après connexion et envoi manuel', async () => {
    render(<App />);
    await connectAndChoose();
    expect(readImage).toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: /Envoyer à l’API/ }));
    await screen.findByText('La vision reste à raccorder');
    expect(screen.getByText('HTTP 503 · perception_unavailable')).toBeTruthy();
    expect(screen.queryByText('2 éléments')).toBeNull();
    expect(localStorage.getItem('apiUrl')).toBe('http://127.0.0.1:8000');
});

it('invalide la connexion et le résultat quand l’adresse API change', async () => {
    render(<App />);
    await connectAndChoose();
    fireEvent.click(screen.getByRole('button', { name: 'Changer de capture' }));
    fireEvent.click(screen.getByRole('button', { name: /Voir un exemple synthétique/ }));
    await openSettings();
    fireEvent.change(screen.getByLabelText('Adresse du serveur'), {
        target: { value: 'https://other.example.org' },
    });
    expect(screen.queryByText('2 éléments')).toBeNull();
    expect(screen.queryByText('Serveur joignable · v0.1.0')).toBeNull();
    openAnalysis();
    expect(
        (screen.getByRole('button', { name: /Envoyer à l’API/ }) as HTMLButtonElement).disabled,
    ).toBe(true);
});

it('transmet la clé en mémoire et l’efface quand le serveur change', async () => {
    const key = 'session-key-for-local-tests-123456789';
    const { unmount } = render(<App />);
    await openSettings();
    const input = screen.getByLabelText('Clé API (si demandée)') as HTMLInputElement;
    expect(input.type).toBe('password');
    fireEvent.change(input, { target: { value: key } });
    await connectAndChoose();
    const [, options] = vi
        .mocked(fetch)
        .mock.calls.find(([url]) => String(url).endsWith('/capabilities'))!;
    expect(new Headers(options?.headers).get('Authorization')).toBe(`Bearer ${key}`);
    expect(JSON.stringify(localStorage)).not.toContain(key);
    expect(JSON.stringify(sessionStorage)).not.toContain(key);
    await openSettings();
    fireEvent.change(screen.getByLabelText('Adresse du serveur'), {
        target: { value: 'https://other.example.org' },
    });
    expect(input.value).toBe('');
    expect(sessionApiHeaders('http://127.0.0.1:8000')).toEqual({});
    expect(screen.queryByText('Serveur joignable · v0.1.0')).toBeNull();
    unmount();
});

it('invalide la connexion quand la clé change et l’oublie à la fermeture', async () => {
    const key = 'session-key-for-local-tests-123456789';
    const { unmount } = render(<App />);
    await openSettings();
    fireEvent.change(screen.getByLabelText('Clé API (si demandée)'), {
        target: { value: key },
    });
    await connectAndChoose();
    await openSettings();
    fireEvent.change(screen.getByLabelText('Clé API (si demandée)'), {
        target: { value: key + '2' },
    });
    expect(screen.queryByText('Serveur joignable · v0.1.0')).toBeNull();
    expect(sessionApiHeaders('http://127.0.0.1:8000')).toEqual({});
    fireEvent.click(screen.getByRole('button', { name: 'Vérifier la connexion' }));
    await screen.findByText('Serveur joignable · v0.1.0');
    expect(sessionApiHeaders('http://127.0.0.1:8000')).toEqual({ Authorization: `Bearer ${key}2` });
    unmount();
    expect(sessionApiHeaders('http://127.0.0.1:8000')).toEqual({});
});

it('ignore un résultat tardif après annulation', async () => {
    render(<App />);
    await connectAndChoose();
    let resolveResponse!: (response: Response) => void;
    let captureId = '';
    vi.mocked(fetch).mockImplementationOnce((url) => {
        captureId = new URL(String(url), 'http://localhost').searchParams.get('capture_id')!;
        return new Promise<Response>((resolve) => {
            resolveResponse = resolve;
        });
    });
    fireEvent.click(screen.getByRole('button', { name: /Envoyer à l’API/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Annuler' }));
    await act(async () => {
        resolveResponse(new Response(JSON.stringify({ ...fixture, capture_id: captureId })));
    });
    expect(screen.getByText('Opération annulée')).toBeTruthy();
    expect(screen.queryByText('2 éléments')).toBeNull();
});

it('conserve la capture et la connexion en passant par Réglages et Équipe', async () => {
    render(<App />);
    await connectAndChoose();
    expect(screen.queryByRole('button', { name: 'Vérifier la connexion' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Équipe' }));
    expect(screen.getByRole('button', { name: 'Charger l’inventaire' })).toBeTruthy();
    await openSettings();
    expect(screen.getByText('Serveur joignable · v0.1.0')).toBeTruthy();
    openAnalysis();
    expect(screen.getByText('capture.png')).toBeTruthy();
    expect(
        (screen.getByRole('button', { name: /Envoyer à l’API/ }) as HTMLButtonElement).disabled,
    ).toBe(false);
    expect(fetch).toHaveBeenCalledTimes(2);
});

it('montre une erreur d’authentification directement dans Réglages', async () => {
    render(<App />);
    await openSettings();
    vi.mocked(fetch).mockImplementation(
        async (url) =>
            new Response(
                JSON.stringify(
                    String(url).endsWith('/health')
                        ? { status: 'ok', version: '0.1.0', model_loaded: false }
                        : {
                              detail: {
                                  code: 'authentication_required',
                                  message: 'Clé API absente ou incorrecte.',
                              },
                          },
                ),
                { status: String(url).endsWith('/health') ? 200 : 401 },
            ),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Vérifier la connexion' }));
    await screen.findByText('Connexion impossible');
    expect(screen.getByRole('alert').textContent).toContain('HTTP 401');
    expect(screen.getByRole('button', { name: 'Réglages' }).getAttribute('aria-pressed')).toBe(
        'true',
    );
    expect(screen.queryByText('API connectée')).toBeNull();
    openAnalysis();
    expect(screen.queryByRole('alert')).toBeNull();
});

it('relie la sélection d’un élément à son repère, sans contacter l’API', () => {
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: /Voir un exemple synthétique/ }));
    const first = screen.getByRole('button', { name: 'Afficher l’élément 1 : Rechercher' });
    const second = screen.getByRole('button', { name: 'Afficher l’élément 2 : Vérifier' });
    expect(first.getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(second);
    expect(second.getAttribute('aria-pressed')).toBe('true');
    expect(
        screen
            .getByRole('button', { name: 'Afficher le repère 2 : Vérifier' })
            .getAttribute('aria-pressed'),
    ).toBe('true');
    fireEvent.keyDown(screen.getByRole('button', { name: 'Afficher le repère 1 : Rechercher' }), {
        key: 'Enter',
    });
    expect(first.getAttribute('aria-pressed')).toBe('true');
    expect(fetch).not.toHaveBeenCalled();
});

it('retire la capture en mémoire sans envoyer d’image au serveur', async () => {
    render(<App />);
    await connectAndChoose();
    const calls = vi.mocked(fetch).mock.calls.length;
    expect(screen.queryByRole('button', { name: /Choisir une image PNG ou JPEG ·/ })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Retirer' }));
    expect(screen.queryByText('capture.png')).toBeNull();
    expect(screen.getByRole('button', { name: /Choisir une image PNG ou JPEG ·/ })).toBeTruthy();
    expect(fetch).toHaveBeenCalledTimes(calls);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:synthetic-test');
});

it('efface explicitement la clé sans lancer une nouvelle connexion', async () => {
    render(<App />);
    await openSettings();
    fireEvent.change(screen.getByLabelText('Clé API (si demandée)'), {
        target: { value: 'session-key-for-local-tests-123456789' },
    });
    fireEvent.submit(
        screen.getByRole('button', { name: 'Vérifier la connexion' }).closest('form')!,
    );
    await screen.findByText('Serveur joignable · v0.1.0');
    const calls = vi.mocked(fetch).mock.calls.length;
    fireEvent.click(screen.getByRole('button', { name: 'Effacer la clé' }));
    expect((screen.getByLabelText('Clé API (si demandée)') as HTMLInputElement).value).toBe('');
    expect(sessionApiHeaders('http://127.0.0.1:8000')).toEqual({});
    expect(screen.queryByText('API connectée')).toBeNull();
    expect(fetch).toHaveBeenCalledTimes(calls);
});
