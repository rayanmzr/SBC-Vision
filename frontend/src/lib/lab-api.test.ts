import { afterEach, expect, it, vi } from 'vitest';
import { apiLabPerceiver } from './lab-api';
import { DEFAULT_API_URL } from './platform';

function response(captureId: string) {
    return {
        schema_version: '0.1',
        capture_id: captureId,
        model_name: 'lab-color-api-v1',
        image: { width: 640, height: 270 },
        elements: [
            {
                id: 'lab-select',
                kind: 'button',
                bbox: { x: 48, y: 174, width: 232, height: 58 },
                confidence: 1,
                actions: ['click'],
            },
        ],
    };
}
const png = () => new Blob(['png pixels'], { type: 'image/png' });
const signal = () => new AbortController().signal;
afterEach(() => vi.unstubAllGlobals());

it('envoie seulement le PNG à la route de perception et utilise un identifiant neuf à chaque image', async () => {
    const identifiers: string[] = [];
    const fetchMock = vi.fn(async (url: string) => {
        const id = new URL(url, 'http://localhost').searchParams.get('capture_id')!;
        identifiers.push(id);
        return new Response(JSON.stringify(response(id)));
    });
    vi.stubGlobal('fetch', fetchMock);
    const perceive = apiLabPerceiver(DEFAULT_API_URL);
    for (let i = 0; i < 2; i++)
        expect((await perceive(png(), { width: 640, height: 270 }, signal())).elements[0].id).toBe(
            'lab-select',
        );
    expect(new Set(identifiers).size).toBe(2);
    const calls = fetchMock.mock.calls as unknown as Array<[string, RequestInit]>;
    for (const [url, options] of calls) {
        expect(url).toContain('/api/v1/perception/analyze?capture_id=');
        expect(url).not.toContain('/solve');
        expect(options.headers).toEqual({ 'Content-Type': 'image/png' });
        expect(options.body).toBeInstanceOf(File);
        expect(await (options.body as File).text()).toBe('png pixels');
        expect(options.credentials).toBe('omit');
    }
});

it.each(['capture', 'dimensions', 'model'])(
    'refuse une réponse associée au mauvais contexte : %s',
    async (fault) => {
        vi.stubGlobal(
            'fetch',
            vi.fn(async (url: string) => {
                const data = response(
                    new URL(url, 'http://localhost').searchParams.get('capture_id')!,
                );
                if (fault === 'capture') data.capture_id = 'old-capture';
                if (fault === 'dimensions') data.image.width = 800;
                if (fault === 'model') data.model_name = 'some-game-model';
                return new Response(JSON.stringify(data));
            }),
        );
        await expect(
            apiLabPerceiver(DEFAULT_API_URL)(png(), { width: 640, height: 270 }, signal()),
        ).rejects.toThrow();
    },
);

it.each([422, 503])(
    'conserve l’erreur HTTP %s sans substituer le détecteur navigateur',
    async (status) => {
        const fetchMock = vi.fn(
            async () =>
                new Response(
                    JSON.stringify({
                        detail: {
                            code: status === 503 ? 'perception_unavailable' : 'scene_unrecognized',
                            message: 'Analyse indisponible.',
                        },
                    }),
                    { status },
                ),
        );
        vi.stubGlobal('fetch', fetchMock);
        await expect(
            apiLabPerceiver(DEFAULT_API_URL)(png(), { width: 640, height: 270 }, signal()),
        ).rejects.toMatchObject({ status });
        expect(fetchMock).toHaveBeenCalledOnce();
    },
);

it('respecte l’annulation avant tout envoi', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    const controller = new AbortController();
    controller.abort();
    await expect(
        apiLabPerceiver(DEFAULT_API_URL)(png(), { width: 640, height: 270 }, controller.signal),
    ).rejects.toThrow();
    expect(fetchMock).not.toHaveBeenCalled();
});
