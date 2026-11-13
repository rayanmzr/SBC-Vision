import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { isLocalLabUrl, nativeLabAdapter } from './lab-adapter';
import { planLocalAction, type Frame } from './controller';
import { activeContext, captureActiveTab, type TabContext } from './tab-capture';
import { perceiveLabImage } from './lab-vision';

vi.mock('./tab-capture', async (original) => ({
    ...(await original<typeof import('./tab-capture')>()),
    activeContext: vi.fn(),
    captureActiveTab: vi.fn(),
}));
vi.mock('./lab-vision', async (original) => ({
    ...(await original<typeof import('./lab-vision')>()),
    perceiveLabImage: vi.fn(),
}));
const context = (): TabContext => ({
    tabId: 7,
    windowId: 3,
    documentId: 'local-document',
    viewport: {
        href: 'http://127.0.0.1:5173/controller-lab.html',
        width: 640,
        height: 360,
        scrollX: 0,
        scrollY: 0,
        pixelRatio: 2,
        visualScale: 1,
        offsetX: 0,
        offsetY: 0,
        timeOrigin: 10,
        visibility: 'visible',
    },
});
const frame = (): Frame => ({
    target: '7:local-document',
    observedAt: Date.now(),
    geometry: { width: 1280, height: 720, context: context() },
    perception: {
        schema_version: '0.1',
        capture_id: 'capture',
        model_name: 'local-color-baseline-v1',
        image: { width: 1280, height: 720 },
        elements: [
            {
                id: 'lab-select',
                kind: 'button',
                bbox: { x: 100, y: 200, width: 200, height: 80 },
                confidence: 1,
                actions: ['click'],
            },
        ],
    },
});
const signal = () => new AbortController().signal;
let execute: ReturnType<typeof vi.fn>;
beforeEach(() => {
    execute = vi.fn(async () => [{ frameId: 0, result: true }]);
    vi.stubGlobal('chrome', { scripting: { executeScript: execute } });
    vi.mocked(activeContext).mockReset().mockResolvedValue(context());
    vi.mocked(captureActiveTab)
        .mockReset()
        .mockResolvedValue({
            file: new File(['pixels'], 'capture.png', { type: 'image/png' }),
            url: 'blob:captured',
            width: 1280,
            height: 720,
            context: context(),
            capturedAt: new Date().toISOString(),
        });
    vi.mocked(perceiveLabImage).mockReset().mockResolvedValue(frame().perception);
    URL.revokeObjectURL = vi.fn();
});
afterEach(() => vi.unstubAllGlobals());

it.each([
    'https://www.ea.com/controller-lab.html',
    'http://evil.test:5173/controller-lab.html',
    'http://127.0.0.1:5173/',
    'http://127.0.0.1:8000/controller-lab.html',
    'http://127.0.0.1:5173/controller-lab.html?next=1',
    'http://user:pass@localhost:5173/controller-lab.html',
    'file:///controller-lab.html',
])('refuse toute cible hors de la page locale exacte : %s', (url) =>
    expect(isLocalLabUrl(url)).toBe(false),
);
it.each(['http://127.0.0.1:5173/controller-lab.html', 'http://localhost:4173/controller-lab.html'])(
    'accepte le laboratoire local : %s',
    (url) => expect(isLocalLabUrl(url)).toBe(true),
);
it('produit le JSON depuis la capture réelle et libère son URL après lecture des pixels', async () => {
    const observed = await nativeLabAdapter().observe(signal());
    expect(observed.target).toBe('7:local-document');
    expect(observed.perception).toEqual(frame().perception);
    expect(perceiveLabImage).toHaveBeenCalledWith(expect.any(File), expect.any(AbortSignal));
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:captured');
});
it('refuse la capture hors laboratoire avant de lire des pixels', async () => {
    const outside = context();
    outside.viewport.href = 'https://www.ea.com/';
    vi.mocked(activeContext).mockResolvedValue(outside);
    await expect(nativeLabAdapter().observe(signal())).rejects.toThrow('page locale');
    expect(captureActiveTab).not.toHaveBeenCalled();
});
it('libère la capture aussi si la vision locale ne reconnaît pas l’écran', async () => {
    vi.mocked(perceiveLabImage).mockRejectedValueOnce(new Error('État ambigu.'));
    await expect(nativeLabAdapter().observe(signal())).rejects.toThrow('ambigu');
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:captured');
});
it('envoie les coordonnées au document précis avec une durée de validité courte', async () => {
    const observed = frame();
    const action = planLocalAction(observed)!;
    await nativeLabAdapter().click(observed, action, signal());
    expect(execute).toHaveBeenCalledWith({
        target: { tabId: 7, documentIds: ['local-document'] },
        func: expect.any(Function),
        args: [100, 120, context().viewport, expect.any(Number)],
    });
    expect(execute.mock.calls[0][0].args[3] - Date.now()).toBeLessThanOrEqual(1000);
});
it('ne clique pas si le document, la géométrie ou l’action ne correspond plus à la capture', async () => {
    const observed = frame();
    const action = planLocalAction(observed)!;
    const changed = context();
    changed.documentId = 'reloaded';
    vi.mocked(activeContext).mockResolvedValueOnce(changed);
    await expect(nativeLabAdapter().click(observed, action, signal())).rejects.toThrow('Contexte');
    await expect(
        nativeLabAdapter().click(observed, { ...action, x: 10 }, signal()),
    ).rejects.toThrow('Action différente');
    expect(execute).not.toHaveBeenCalled();
});
it('ne transforme pas un refus de Chrome en clic confirmé', async () => {
    execute.mockRejectedValueOnce(new Error('Permission refusée.'));
    const observed = frame();
    await expect(
        nativeLabAdapter().click(observed, planLocalAction(observed)!, signal()),
    ).rejects.toThrow('Permission');
});
