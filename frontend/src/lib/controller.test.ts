import { afterEach, expect, it, vi } from 'vitest';
import { planLocalAction, runController, type Frame, type Mode } from './controller';

export function frame(stage = 0): Frame {
    const id = ['lab-select', 'lab-place', 'lab-done'][stage];
    return {
        target: 'local-doc',
        observedAt: Date.now(),
        geometry: {
            width: 1280,
            height: 720,
            context: {
                tabId: 1,
                windowId: 1,
                documentId: 'doc',
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
            },
        },
        perception: {
            schema_version: '0.1',
            capture_id: crypto.randomUUID(),
            model_name: 'local-color-baseline-v1',
            image: { width: 1280, height: 720 },
            elements: [
                {
                    id,
                    kind: stage === 2 ? 'text' : 'button',
                    bbox: { x: 20 + 200 * stage, y: 100, width: 80, height: 50 },
                    confidence: 1,
                    actions: stage === 2 ? [] : ['click'],
                },
            ],
        },
    };
}
function harness(effect: 'normal' | 'nothing' | 'unexpected' = 'normal') {
    let stage = 0;
    return {
        observe: vi.fn(async () => frame(stage)),
        click: vi.fn(async () => {
            stage = effect === 'normal' ? stage + 1 : effect === 'unexpected' ? 2 : stage;
        }),
    };
}
const signal = () => new AbortController().signal;
afterEach(() => vi.useRealTimers());

it('effectue deux clics et vérifie chaque transition depuis une nouvelle observation', async () => {
    const adapter = harness();
    const result = await runController(adapter, 'local', 2, signal());
    expect(result.status).toBe('completed');
    expect(result.clicks).toBe(2);
    expect(adapter.observe).toHaveBeenCalledTimes(5);
    expect(adapter.click.mock.calls[0]).toEqual([
        expect.objectContaining({ target: 'local-doc' }),
        { type: 'click', elementId: 'lab-select', x: 30, y: 62.5, expected: 'lab-place' },
        expect.any(AbortSignal),
    ]);
    expect(result.entries.filter((entry) => entry.kind === 'verified')).toHaveLength(3);
    expect(result.entries.some((entry) => entry.perception?.elements[0].id === 'lab-done')).toBe(
        true,
    );
});

it.each(['observation', 'simulation'] as Mode[])(
    'le mode %s ne clique pas et ne prétend pas avoir vérifié une transition',
    async (mode) => {
        const adapter = harness();
        const result = await runController(adapter, mode, 2, signal());
        expect(result.status).toBe(mode === 'observation' ? 'observed' : 'simulated');
        expect(result.clicks).toBe(0);
        expect(adapter.click).not.toHaveBeenCalled();
        expect(adapter.observe).toHaveBeenCalledOnce();
        expect(result.entries.some((entry) => entry.kind === 'verified')).toBe(false);
    },
);

it.each(['nothing', 'unexpected'] as const)(
    'arrête sans réessayer si le clic produit %s',
    async (effect) => {
        const adapter = harness(effect);
        const result = await runController(adapter, 'local', 5, signal());
        expect(result.status).toBe('diverged');
        expect(result.clicks).toBe(1);
        expect(adapter.click).toHaveBeenCalledOnce();
    },
);

it('s’arrête au budget sans présenter un parcours incomplet comme réussi', async () => {
    const adapter = harness();
    const result = await runController(adapter, 'local', 1, signal());
    expect(result.status).toBe('step_limit');
    expect(result.clicks).toBe(1);
    expect(adapter.observe).toHaveBeenCalledTimes(3);
});

it.each([0, -1, 1.5, 6, NaN])('refuse le budget %s avant toute capture', async (budget) => {
    const adapter = harness();
    expect((await runController(adapter, 'local', budget, signal())).status).toBe('failed');
    expect(adapter.observe).not.toHaveBeenCalled();
});

it.each(['target', 'geometry', 'box'] as const)(
    'ne clique pas si %s change dans la capture juste avant action',
    async (change) => {
        const adapter = harness();
        const fresh = frame();
        if (change === 'target') fresh.target = 'other-doc';
        if (change === 'geometry') fresh.geometry.context.viewport.scrollY = 20;
        if (change === 'box') fresh.perception.elements[0].bbox.x += 10;
        adapter.observe.mockResolvedValueOnce(frame()).mockResolvedValueOnce(fresh);
        expect((await runController(adapter, 'local', 2, signal())).status).toBe('diverged');
        expect(adapter.click).not.toHaveBeenCalled();
    },
);

it.each(['stale', 'ambiguous', 'confidence', 'outside', 'forbidden', 'actions', 'model'] as const)(
    'refuse une décision invalide : %s',
    (fault) => {
        const observed = frame();
        if (fault === 'stale') observed.observedAt -= 6000;
        if (fault === 'ambiguous')
            observed.perception.elements.push({ ...observed.perception.elements[0], id: 'second' });
        if (fault === 'confidence') observed.perception.elements[0].confidence = 0.9;
        if (fault === 'outside') observed.perception.elements[0].bbox.x = 1300;
        if (fault === 'forbidden') observed.perception.elements[0].id = 'submit-sbc';
        if (fault === 'actions') observed.perception.elements[0].actions = ['fill'];
        if (fault === 'model') observed.perception.model_name = 'real-game-detector';
        expect(() => planLocalAction(observed)).toThrow();
    },
);

it('ne clique pas après une interruption pendant la capture et ignore son retour tardif', async () => {
    let complete!: (value: Frame) => void;
    const adapter = harness();
    adapter.observe.mockImplementationOnce(
        () =>
            new Promise((resolve) => {
                complete = resolve;
            }),
    );
    const controller = new AbortController();
    const running = runController(adapter, 'local', 2, controller.signal);
    controller.abort();
    const result = await running;
    complete(frame());
    await Promise.resolve();
    expect(result.status).toBe('cancelled');
    expect(adapter.click).not.toHaveBeenCalled();
    expect(result.entries.some((entry) => entry.kind === 'verified')).toBe(false);
});

it('arrête une capture qui ne répond pas après huit secondes', async () => {
    vi.useFakeTimers();
    const adapter = harness();
    adapter.observe.mockImplementationOnce(() => new Promise(() => {}));
    const running = runController(adapter, 'local', 2, signal());
    await vi.advanceTimersByTimeAsync(8001);
    const result = await running;
    expect(result.status).toBe('failed');
    expect(result.entries.at(-1)?.message).toContain('Délai');
    expect(adapter.click).not.toHaveBeenCalled();
});

it('ne prétend pas réussir après une erreur de capture ou de clic', async () => {
    const adapter = harness();
    adapter.click.mockRejectedValueOnce(new Error('Permission refusée.'));
    const result = await runController(adapter, 'local', 2, signal());
    expect(result.status).toBe('failed');
    expect(result.clicks).toBe(0);
    expect(result.attempts).toBe(1);
    expect(adapter.click).toHaveBeenCalledOnce();
});

it('refuse une ancienne capture présentée comme une nouvelle observation', async () => {
    const adapter = harness();
    adapter.observe.mockResolvedValue(frame());
    const result = await runController(adapter, 'local', 2, signal());
    expect(result.status).toBe('failed');
    expect(result.entries.at(-1)?.message).toContain('capture réutilisée');
    expect(adapter.click).not.toHaveBeenCalled();
});

it('distingue une tentative déjà commencée d’un clic confirmé après interruption', async () => {
    const adapter = harness();
    const controller = new AbortController();
    adapter.click.mockImplementationOnce(async () => {
        controller.abort();
    });
    const result = await runController(adapter, 'local', 2, controller.signal);
    expect(result.status).toBe('cancelled');
    expect(result.attempts).toBe(1);
    expect(result.clicks).toBe(0);
    expect(result.entries.some((entry) => entry.kind === 'verified')).toBe(false);
});
