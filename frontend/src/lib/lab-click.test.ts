// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { nativeLabAdapter } from './lab-adapter';
import { activeContext } from './tab-capture';
import { planLocalAction, type Frame } from './controller';

vi.mock('./tab-capture', async (original) => ({
    ...(await original<typeof import('./tab-capture')>()),
    activeContext: vi.fn(),
}));
let observed: Frame;
let canvas: HTMLCanvasElement;
let clicks: MouseEvent[];
let execute: ReturnType<typeof vi.fn>;
beforeEach(() => {
    canvas = document.createElement('canvas');
    canvas.dataset.sbcControllerLab = 'v1';
    document.body.append(canvas);
    clicks = [];
    canvas.addEventListener('click', (event) => clicks.push(event));
    observed = {
        target: 'local',
        observedAt: Date.now(),
        geometry: {
            width: 1280,
            height: 720,
            context: {
                tabId: 7,
                windowId: 3,
                documentId: 'document-1',
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
                    timeOrigin: performance.timeOrigin,
                    visibility: 'visible',
                },
            },
        },
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
    };
    vi.mocked(activeContext).mockReset().mockResolvedValue(observed.geometry.context);
    vi.stubGlobal('location', new URL(observed.geometry.context.viewport.href));
    vi.stubGlobal('innerWidth', 640);
    vi.stubGlobal('innerHeight', 360);
    vi.stubGlobal('scrollX', 0);
    vi.stubGlobal('scrollY', 0);
    vi.stubGlobal('devicePixelRatio', 2);
    vi.stubGlobal('visualViewport', undefined);
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible');
    document.elementFromPoint = vi.fn(() => canvas);
    execute = vi.fn(async ({ func, args }) => [{ frameId: 0, result: func(...args) }]);
    vi.stubGlobal('chrome', { scripting: { executeScript: execute } });
});
afterEach(() => {
    document.body.replaceChildren();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
});
const perform = () =>
    nativeLabAdapter().click(observed, planLocalAction(observed)!, new AbortController().signal);

it('l’actionneur injecté clique le canevas au point CSS calculé, avec un événement synthétique', async () => {
    await perform();
    expect(clicks).toHaveLength(1);
    expect(clicks[0].clientX).toBe(100);
    expect(clicks[0].clientY).toBe(120);
    expect(clicks[0].isTrusted).toBe(false);
});
it.each(['page', 'scroll', 'zoom', 'hidden', 'overlay', 'marker', 'expired'])(
    'l’actionneur refuse si %s a changé juste avant l’événement',
    async (fault) => {
        if (fault === 'page') vi.stubGlobal('location', new URL('https://www.ea.com/'));
        if (fault === 'scroll') vi.stubGlobal('scrollY', 50);
        if (fault === 'zoom') vi.stubGlobal('devicePixelRatio', 1.25);
        if (fault === 'hidden')
            vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
        if (fault === 'overlay')
            vi.mocked(document.elementFromPoint).mockReturnValue(document.createElement('button'));
        if (fault === 'marker') delete canvas.dataset.sbcControllerLab;
        if (fault === 'expired')
            execute.mockImplementationOnce(async ({ func, args }) => {
                vi.spyOn(Date, 'now').mockReturnValue(args[3] + 1);
                return [{ frameId: 0, result: func(...args) }];
            });
        await expect(perform()).rejects.toThrow();
        expect(clicks).toHaveLength(0);
    },
);
