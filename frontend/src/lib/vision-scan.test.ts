import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { requestJson } from './api';
import { activeContext, captureActiveTab, type TabCapture, type TabContext } from './tab-capture';
import { scanVision, visionPointInTab, type VisionFrame } from './vision-scan';

vi.mock('./api', () => ({ requestJson: vi.fn() }));
vi.mock('./tab-capture', async (original) => ({
    ...(await original<typeof import('./tab-capture')>()),
    activeContext: vi.fn(),
    captureActiveTab: vi.fn(),
}));
const context: TabContext = {
    tabId: 7,
    windowId: 3,
    documentId: 'synthetic-document',
    viewport: {
        href: 'https://www.ea.com/ea-sports-fc/ultimate-team/web-app/',
        width: 1000,
        height: 600,
        scrollX: 0,
        scrollY: 0,
        pixelRatio: 1,
        visualScale: 1,
        offsetX: 0,
        offsetY: 0,
        timeOrigin: 10,
        visibility: 'visible',
    },
};
const area = { x: 100, y: 120, width: 500, height: 350 };
const control = { x: 200, y: 500, width: 80, height: 25 };
let frames: Partial<VisionFrame>[], execute: ReturnType<typeof vi.fn>;

beforeEach(() => {
    vi.useFakeTimers();
    let sequence = 0;
    vi.stubGlobal('crypto', {
        randomUUID: () => `synthetic-${++sequence}`,
        subtle: { digest: vi.fn(async () => new Uint8Array(32).buffer) },
    });
    frames = [];
    execute = vi.fn(async () => [{ frameId: 0, result: true }]);
    vi.stubGlobal('chrome', { scripting: { executeScript: execute } });
    vi.stubGlobal(
        'createImageBitmap',
        vi.fn(async () => ({ close: vi.fn() })),
    );
    vi.stubGlobal(
        'OffscreenCanvas',
        class {
            getContext() {
                return { drawImage: vi.fn(), getImageData: () => ({ data: new Uint8Array(32) }) };
            }
        },
    );
    URL.revokeObjectURL = vi.fn();
    vi.mocked(activeContext).mockReset().mockResolvedValue(context);
    vi.mocked(captureActiveTab)
        .mockReset()
        .mockImplementation(
            async () =>
                ({
                    context,
                    width: 1000,
                    height: 600,
                    url: 'blob:synthetic',
                    file: new File(['synthetic-pixels'], 'screen.png', { type: 'image/png' }),
                }) as TabCapture,
        );
    vi.mocked(requestJson)
        .mockReset()
        .mockImplementation(async (_base, path, init) => {
            if (path.includes('/club-analyze'))
                return {
                    capture_id: new URL(path, 'http://localhost').searchParams.get('capture_id'),
                    source: 'vision',
                    model_name: 'synthetic-test',
                    image: { width: 1000, height: 600 },
                    scene: 'players',
                    screen_hash: 'a'.repeat(64),
                    image_sha256: 'b'.repeat(64),
                    controls: {},
                    list_bbox: area,
                    rows: [],
                    ocr: null,
                    ...frames.shift(),
                };
            const body = JSON.parse(String(init?.body));
            return {
                source: 'vision',
                captures: body.capture_ids.length,
                readings: 2,
                identified: 1,
                uncertain: 3,
                complete: body.complete,
                inventory_updated: false,
            };
        });
});
afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
});
async function run(maxFrames?: number) {
    const pending = scanVision(
        'http://localhost',
        new AbortController().signal,
        vi.fn(),
        maxFrames,
    );
    const [result] = await Promise.all([pending, vi.runAllTimersAsync()]);
    return result;
}

it('parcourt previous, défilement et next depuis le JSON vision, sans injecter de lecteur HTML', async () => {
    frames = [
        { controls: { previous: control, next: control } },
        { controls: { next: control } },
        { controls: { next: control } },
        { controls: { next: control } },
        {},
        {},
        {},
    ];
    const result = await run();
    expect(result.complete).toBe(true);
    expect(result.captures).toBe(7);
    expect(execute.mock.calls.every(([arg]) => arg.func === visionPointInTab)).toBe(true);
    const calls = vi.mocked(requestJson).mock.calls;
    expect(calls.every(([, path]) => /club-analyze|vision-scan/.test(path))).toBe(true);
    const saved = JSON.parse(String(calls.at(-1)![2]?.body));
    expect(saved.actions.map((a: { action: string }) => a.action)).toEqual([
        'previous',
        'up',
        'down',
        'next',
        'up',
        'down',
    ]);
    expect(saved).not.toHaveProperty('cards');
});

it('s’arrête sans secours HTML en cas d’observation invalide ou d’erreur OCR', async () => {
    vi.mocked(requestJson).mockRejectedValueOnce(new Error('OCR indisponible'));
    await expect(run()).rejects.toThrow('OCR indisponible');
    expect(execute).not.toHaveBeenCalled();
    expect(requestJson).toHaveBeenCalledTimes(1);
    frames = [{ source: 'dom' as 'vision' }];
    await expect(run()).rejects.toThrow('non conforme');
    expect(execute).not.toHaveBeenCalled();
});

it('conserve un relevé partiel lorsque le budget de captures est atteint', async () => {
    frames = [{}, {}, { screen_hash: 'c'.repeat(64) }];
    const result = await run(3);
    expect(result.complete).toBe(false);
    expect(result.captures).toBe(3);
});

it('interdit l’action si le document ou sa géométrie change après la capture', async () => {
    vi.mocked(activeContext)
        .mockResolvedValueOnce(context)
        .mockResolvedValueOnce(context)
        .mockResolvedValueOnce({ ...context, documentId: 'other' });
    await expect(run()).rejects.toThrow('onglet a changé');
    expect(execute).not.toHaveBeenCalled();
});

it('ne clique pas si les pixels du bouton ont changé, même avec une liste identique', async () => {
    frames = [{ controls: { previous: control } }];
    vi.mocked(crypto.subtle.digest)
        .mockResolvedValueOnce(new Uint8Array(32).buffer)
        .mockResolvedValueOnce(new Uint8Array(32).buffer)
        .mockResolvedValueOnce(new Uint8Array(32).buffer)
        .mockResolvedValueOnce(new Uint8Array(32).fill(1).buffer);
    await expect(run()).rejects.toThrow('image a changé');
    expect(execute).not.toHaveBeenCalled();
});

it('ne répète pas Club lorsque Players est illisible sur le menu du club', async () => {
    frames = [{ scene: 'club', controls: { club: control } }];
    await expect(run()).rejects.toThrow('vision ne reconnaît pas');
    expect(execute).not.toHaveBeenCalled();
});

it('l’actionneur utilise le point et la géométrie, sans lire texte, HTML ou sélecteurs', () => {
    vi.stubGlobal('location', new URL(context.viewport.href));
    vi.stubGlobal('innerWidth', 1000);
    vi.stubGlobal('innerHeight', 600);
    vi.stubGlobal(
        'MouseEvent',
        class {
            constructor(public type: string) {}
        },
    );
    const target = {
        scrollHeight: 1000,
        clientHeight: 300,
        parentElement: null,
        scrollBy: vi.fn(),
        dispatchEvent: vi.fn(),
        get textContent() {
            throw new Error('Lecture interdite');
        },
        get innerHTML() {
            throw new Error('Lecture interdite');
        },
    };
    vi.stubGlobal('document', {
        elementFromPoint: vi.fn(() => target),
        get querySelector() {
            throw new Error('Sélecteur interdit');
        },
    });
    expect(visionPointInTab({ type: 'click', x: 30, y: 40, amount: 0 })).toBe(true);
    expect(target.dispatchEvent.mock.calls.map(([e]) => e.type)).toEqual([
        'mousedown',
        'mouseup',
        'click',
    ]);
    visionPointInTab({ type: 'scroll', x: 30, y: 40, amount: 200 });
    expect(target.scrollBy).toHaveBeenCalledWith({ top: 200, behavior: 'instant' });
    expect(() => visionPointInTab({ type: 'click', x: NaN, y: 40, amount: 0 })).toThrow(
        'invalides',
    );
});
