// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import App from './App';
import { captureActiveTab, type TabCapture } from './lib/tab-capture';
import perception from '../../data/fixtures/perception.synthetic.json';

vi.mock('./lib/tab-capture', async (original) => ({
    ...(await original<typeof import('./lib/tab-capture')>()),
    captureActiveTab: vi.fn(),
}));
const captured = (): TabCapture => ({
    file: new File(['png pixels'], 'capture-onglet.png', { type: 'image/png' }),
    url: 'blob:captured-tab',
    width: 1280,
    height: 720,
    capturedAt: '2026-11-13T12:00:00Z',
    context: {
        tabId: 7,
        windowId: 3,
        documentId: 'doc',
        viewport: {
            href: 'https://example.test/club?private=value',
            width: 640,
            height: 360,
            scrollX: 0,
            scrollY: 100,
            pixelRatio: 2,
            visualScale: 1,
            offsetX: 0,
            offsetY: 0,
            timeOrigin: 10,
            visibility: 'visible',
        },
    },
});
beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal('chrome', {
        runtime: { id: 'test' },
        storage: { local: { get: vi.fn(async () => ({})), set: vi.fn(async () => {}) } },
    });
    URL.revokeObjectURL = vi.fn();
    vi.mocked(captureActiveTab).mockReset().mockResolvedValue(captured());
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
});
afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
});
async function ready() {
    render(<App />);
    await waitFor(() =>
        expect(
            (screen.getByRole('button', { name: 'Vérifier la connexion' }) as HTMLButtonElement)
                .disabled,
        ).toBe(false),
    );
}

it('conserve la capture en mémoire et attend le bouton d’envoi avant de contacter la perception', async () => {
    await ready();
    fireEvent.click(screen.getByRole('button', { name: 'Capturer l’onglet actif' }));
    await screen.findByText('Capture locale de l’onglet');
    expect(screen.getByText('https://example.test')).toBeTruthy();
    expect(screen.getByText(/Zone visible : 640 × 360 px CSS/)).toBeTruthy();
    expect(fetch).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Vérifier la connexion' }));
    await screen.findByText('Serveur joignable · v0.1.0');
    fireEvent.click(screen.getByRole('button', { name: /Envoyer à l’API/ }));
    await screen.findByText('La vision reste à raccorder');
    const calls = vi.mocked(fetch).mock.calls;
    expect(String(calls.at(-1)![0])).toContain('/api/v1/perception/analyze?capture_id=');
    expect(calls.at(-1)![1]?.body).toBeInstanceOf(File);
    expect(calls.at(-1)![1]?.headers).toEqual({ 'Content-Type': 'image/png' });
    expect(JSON.stringify(calls)).not.toContain('private=value');
});

it('retire l’ancien résultat si la capture échoue, sans lui substituer une image fictive', async () => {
    await ready();
    fireEvent.click(screen.getByRole('button', { name: /Voir un exemple synthétique/ }));
    expect(screen.getByText('2 éléments')).toBeTruthy();
    vi.mocked(captureActiveTab).mockRejectedValueOnce(new Error('L’onglet a changé.'));
    fireEvent.click(screen.getByRole('button', { name: 'Capturer l’onglet actif' }));
    await screen.findByText('Capture impossible');
    expect(screen.queryByText('2 éléments')).toBeNull();
    expect(screen.queryByText('Capture locale de l’onglet')).toBeNull();
});

it('affiche le centre en pixels CSS à partir du JSON, en mode observation sans exécuter d’action', async () => {
    await ready();
    fireEvent.click(screen.getByRole('button', { name: 'Capturer l’onglet actif' }));
    await screen.findByText('Capture locale de l’onglet');
    fireEvent.click(screen.getByRole('button', { name: 'Vérifier la connexion' }));
    await screen.findByText('Serveur joignable · v0.1.0');
    vi.mocked(fetch).mockImplementationOnce(
        async (url) =>
            new Response(
                JSON.stringify({
                    ...perception,
                    capture_id: new URL(String(url)).searchParams.get('capture_id'),
                }),
            ),
    );
    fireEvent.click(screen.getByRole('button', { name: /Envoyer à l’API/ }));
    await screen.findByText('Centre dans la page : x 95.0 · y 50.0 px CSS · observation');
    expect(
        screen.getByText('Centre dans la page : x 540.0 · y 332.0 px CSS · observation'),
    ).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Vérifier' })).toBeNull();
});

it('ignore une capture tardive après annulation et libère son aperçu', async () => {
    await ready();
    let complete!: (result: TabCapture) => void;
    vi.mocked(captureActiveTab).mockImplementationOnce(
        () =>
            new Promise((resolve) => {
                complete = resolve;
            }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Capturer l’onglet actif' }));
    fireEvent.click(screen.getByRole('button', { name: 'Annuler' }));
    await act(async () => complete(captured()));
    expect(screen.getByText('Opération annulée')).toBeTruthy();
    expect(screen.queryByText('Capture locale de l’onglet')).toBeNull();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:captured-tab');
});
