import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { readImage } from './api';
import {
    captureActiveTab,
    imagePointToViewport,
    validateViewport,
    type TabContext,
    type Viewport,
} from './tab-capture';

vi.mock('./api', async (original) => ({
    ...(await original<typeof import('./api')>()),
    readImage: vi.fn(),
}));
const viewport = (): Viewport => ({
    href: 'https://example.test/club',
    width: 1000,
    height: 600,
    scrollX: 0,
    scrollY: 480,
    pixelRatio: 2,
    visualScale: 1,
    offsetX: 0,
    offsetY: 0,
    timeOrigin: 10,
    visibility: 'visible',
});
const tab = () => ({ id: 7, windowId: 3, active: true, status: 'complete', url: viewport().href });
const scriptResult = (value = viewport(), documentId = 'document-1') => [
    { frameId: 0, documentId, result: value },
];
let query: ReturnType<typeof vi.fn>;
let capture: ReturnType<typeof vi.fn>;
let execute: ReturnType<typeof vi.fn>;

beforeEach(() => {
    vi.useFakeTimers();
    query = vi.fn(async () => [tab()]);
    capture = vi.fn(async () => 'data:image/png;base64,cGl4ZWxz');
    execute = vi.fn(async () => scriptResult());
    vi.stubGlobal('chrome', {
        runtime: { id: 'test-extension' },
        tabs: { query, captureVisibleTab: capture },
        scripting: { executeScript: execute },
    });
    vi.mocked(readImage)
        .mockReset()
        .mockResolvedValue({ url: 'blob:tab-test', width: 2000, height: 1200 });
    URL.revokeObjectURL = vi.fn();
});
afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
});

async function take(signal = new AbortController().signal) {
    const pending = captureActiveTab(signal);
    const [result] = await Promise.all([pending, vi.runAllTimersAsync()]);
    return result;
}

it('capture la zone visible, conserve son repère et ne transmet ni URL ni image au réseau', async () => {
    const network = vi.fn();
    vi.stubGlobal('fetch', network);
    const result = await take();
    expect(capture).toHaveBeenCalledWith(3, { format: 'png' });
    expect(result.context).toEqual({
        tabId: 7,
        windowId: 3,
        documentId: 'document-1',
        viewport: viewport(),
    });
    expect(result.width).toBe(2000);
    expect(result.file.type).toBe('image/png');
    expect(await result.file.text()).toBe('pixels');
    expect(execute).toHaveBeenCalledTimes(2);
    expect(execute.mock.calls[0][0].target).toEqual({ tabId: 7, frameIds: [0] });
    expect(network).not.toHaveBeenCalled();
});

it('refuse l’aperçu web et les pages internes de Chrome', async () => {
    vi.stubGlobal('chrome', undefined);
    await expect(take()).rejects.toThrow('extension Chrome installée');
    vi.stubGlobal('chrome', {
        runtime: { id: 'test' },
        tabs: { query, captureVisibleTab: capture },
    });
    query.mockResolvedValue([{ ...tab(), url: 'chrome://extensions/' }]);
    await expect(take()).rejects.toThrow('HTTP ou HTTPS');
    expect(capture).not.toHaveBeenCalled();
});

it.each(['scroll', 'size', 'zoom', 'navigation', 'reload', 'tab'])(
    'refuse un changement de contexte pendant la capture : %s',
    async (change) => {
        const after = viewport();
        if (change === 'scroll') after.scrollY++;
        if (change === 'size') after.width++;
        if (change === 'zoom') after.pixelRatio = 2.5;
        if (change === 'navigation') after.href += '?next=1';
        execute
            .mockResolvedValueOnce(scriptResult())
            .mockResolvedValueOnce(
                scriptResult(after, change === 'reload' ? 'document-2' : 'document-1'),
            );
        if (change === 'navigation')
            query
                .mockResolvedValueOnce([tab()])
                .mockResolvedValueOnce([{ ...tab(), url: after.href }]);
        if (change === 'tab')
            query.mockResolvedValueOnce([tab()]).mockResolvedValueOnce([{ ...tab(), id: 8 }]);
        await expect(take()).rejects.toThrow('changé pendant la capture');
        expect(readImage).not.toHaveBeenCalled();
    },
);

it('refuse un document non identifiable, invisible ou encore en chargement', async () => {
    execute.mockResolvedValueOnce(scriptResult(viewport(), ''));
    await expect(take()).rejects.toThrow('identifié');
    execute.mockResolvedValueOnce(scriptResult({ ...viewport(), visibility: 'hidden' }));
    await expect(take()).rejects.toThrow('géométrie');
    query.mockResolvedValueOnce([{ ...tab(), status: 'loading' }]);
    await expect(take()).rejects.toThrow('chargement');
    expect(capture).not.toHaveBeenCalled();
});

it('libère le verrou après un refus des permissions et permet de réessayer', async () => {
    execute.mockRejectedValueOnce(new Error('Accès à l’onglet refusé.'));
    await expect(take()).rejects.toThrow('refusé');
    await expect(take()).resolves.toMatchObject({ width: 2000 });
});

it('ignore la fin d’une capture native après annulation et interdit les captures concurrentes', async () => {
    let complete!: (value: string) => void;
    capture.mockImplementationOnce(
        () =>
            new Promise<string>((resolve) => {
                complete = resolve;
            }),
    );
    const controller = new AbortController();
    const pending = captureActiveTab(controller.signal);
    const cancelled = expect(pending).rejects.toThrow('annulée');
    await vi.runAllTimersAsync();
    await expect(captureActiveTab(new AbortController().signal)).rejects.toThrow('déjà en cours');
    controller.abort();
    complete('data:image/png;base64,cGl4ZWxz');
    await cancelled;
    expect(readImage).not.toHaveBeenCalled();
});

it('espace les captures pour rester sous la limite de deux appels par seconde', async () => {
    const moments: number[] = [];
    capture.mockImplementation(async () => {
        moments.push(performance.now());
        return 'data:image/png;base64,cGl4ZWxz';
    });
    await take();
    await take();
    expect(moments[1] - moments[0]).toBeGreaterThanOrEqual(600);
});

it('révoque l’aperçu si les dimensions décodées ne correspondent pas à la page', async () => {
    vi.mocked(readImage).mockResolvedValueOnce({ url: 'blob:bad-size', width: 2000, height: 700 });
    await expect(take()).rejects.toThrow('dimensions');
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:bad-size');
});

it('rejette une capture non PNG et ne lit pas sa charge comme une URL réseau', async () => {
    capture.mockResolvedValueOnce('https://example.test/screenshot.png');
    await expect(take()).rejects.toThrow('PNG');
    expect(readImage).not.toHaveBeenCalled();
});

it('convertit les pixels Retina en coordonnées du viewport sans ajouter le défilement', () => {
    const context: TabContext = {
        tabId: 7,
        windowId: 3,
        documentId: 'document-1',
        viewport: viewport(),
    };
    const point = imagePointToViewport(
        { width: 2000, height: 1200, context },
        { x: 200, y: 100, width: 100, height: 80 },
    );
    expect(point).toEqual({ x: 125, y: 70 });
    expect(
        imagePointToViewport(
            { width: 2500, height: 1500, context },
            { x: 250, y: 125, width: 125, height: 100 },
        ),
    ).toEqual(point);
});

it.each([
    { x: -1, y: 0, width: 10, height: 10 },
    { x: 1995, y: 0, width: 10, height: 10 },
    { x: 0, y: 0, width: 0, height: 10 },
    { x: NaN, y: 0, width: 10, height: 10 },
])('refuse les coordonnées hors capture ou non finies : %j', (box) => {
    const context: TabContext = { tabId: 7, windowId: 3, documentId: 'doc', viewport: viewport() };
    expect(() => imagePointToViewport({ width: 2000, height: 1200, context }, box)).toThrow(
        'boîte',
    );
});

it('refuse un zoom tactile qui décale la zone visible', () => {
    expect(() => validateViewport({ ...viewport(), visualScale: 1.5 })).toThrow('zoom tactile');
});
