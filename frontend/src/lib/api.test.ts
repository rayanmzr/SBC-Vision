import { afterEach, describe, expect, it, vi } from 'vitest';
import fixture from '../../../data/fixtures/perception.synthetic.json';
import { analyzeImage, ApiError, checkConnection, validateFile, validatePerception } from './api';
import { DEFAULT_API_URL, normalizeApiUrl } from './platform';

afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
});

describe('contrat partagé avec Python', () => {
    it('accepte la fixture versionnée et une analyse sans détection', () => {
        expect(validatePerception(fixture).elements).toHaveLength(2);
        expect(validatePerception({ ...fixture, elements: [] }).elements).toEqual([]);
    });

    it.each(['outside', 'duplicate', 'action', 'version', 'extra', 'confidence'])(
        'refuse une réponse inutilisable : %s',
        (caseName) => {
            const data = structuredClone(fixture);
            if (caseName === 'outside') data.elements[0].bbox.x = data.image.width;
            if (caseName === 'duplicate') data.elements.push(data.elements[0]);
            if (caseName === 'action') data.elements[0].actions = ['fill', 'fill'];
            if (caseName === 'version') data.schema_version = '99';
            if (caseName === 'extra') Object.assign(data, { unexpected: true });
            if (caseName === 'confidence') data.elements[0].confidence = 1.5;
            expect(() => validatePerception(data)).toThrow(ApiError);
        },
    );

    it('refuse les réponses associées à une autre capture', () => {
        expect(() =>
            validatePerception(fixture, { captureId: 'other', width: 1280, height: 720 }),
        ).toThrow('autre capture');
        expect(() =>
            validatePerception(fixture, { captureId: fixture.capture_id, width: 640, height: 360 }),
        ).toThrow('dimensions');
    });
});

describe('transport HTTP', () => {
    it('distingue serveur joignable et perception indisponible', async () => {
        vi.stubGlobal(
            'fetch',
            vi.fn(
                async (url: string) =>
                    new Response(
                        JSON.stringify(
                            url.endsWith('/health')
                                ? { status: 'ok', version: '0.1.0', model_loaded: false }
                                : { perception: false, ocr: false },
                        ),
                    ),
            ),
        );
        await expect(
            checkConnection(DEFAULT_API_URL, new AbortController().signal),
        ).resolves.toMatchObject({ modelLoaded: false, perception: false });
    });

    it('transmet le fichier binaire, un identifiant neuf et aucun cookie', async () => {
        const file = new File(['test pixels'], 'example.png', { type: 'image/png' });
        const fetchMock = vi.fn(async (url: string) => {
            const id = new URL(url, 'http://localhost').searchParams.get('capture_id');
            return new Response(JSON.stringify({ ...fixture, capture_id: id }));
        });
        vi.stubGlobal('fetch', fetchMock);
        const response = await analyzeImage(
            DEFAULT_API_URL,
            file,
            { width: 1280, height: 720 },
            new AbortController().signal,
        );
        expect(response.elements).toHaveLength(2);
        const options = (fetchMock.mock.calls as unknown as Array<[string, RequestInit]>)[0][1];
        expect(options.body).toBe(file);
        expect(options.credentials).toBe('omit');
        expect(options.headers).toEqual({ 'Content-Type': 'image/png' });
        expect(response.capture_id).not.toContain('example.png');
    });

    it('conserve une erreur 503 au lieu de fabriquer une détection vide', async () => {
        vi.stubGlobal(
            'fetch',
            vi.fn(
                async () =>
                    new Response(
                        JSON.stringify({
                            detail: { code: 'perception_unavailable', message: 'Pipeline absent.' },
                        }),
                        { status: 503 },
                    ),
            ),
        );
        await expect(
            analyzeImage(
                DEFAULT_API_URL,
                new File(['x'], 'x.png', { type: 'image/png' }),
                { width: 1280, height: 720 },
                new AbortController().signal,
            ),
        ).rejects.toMatchObject({ status: 503, code: 'perception_unavailable' });
    });

    it('refuse une réponse HTML ou une santé incompatible', async () => {
        vi.stubGlobal(
            'fetch',
            vi.fn(async () => new Response('<html>Proxy error</html>', { status: 502 })),
        );
        await expect(
            checkConnection(DEFAULT_API_URL, new AbortController().signal),
        ).rejects.toMatchObject({ code: 'invalid_response' });
        vi.stubGlobal(
            'fetch',
            vi.fn(async () => new Response('{}')),
        );
        await expect(
            checkConnection(DEFAULT_API_URL, new AbortController().signal),
        ).rejects.toMatchObject({ code: 'invalid_response' });
    });

    it('borne les requêtes bloquées par un délai', async () => {
        vi.useFakeTimers();
        vi.stubGlobal(
            'fetch',
            vi.fn(
                (_url: string, init: RequestInit) =>
                    new Promise((_resolve, reject) => {
                        init.signal?.addEventListener('abort', () =>
                            reject(new DOMException('Aborted', 'AbortError')),
                        );
                    }),
            ),
        );
        const assertion = expect(
            checkConnection(DEFAULT_API_URL, new AbortController().signal),
        ).rejects.toMatchObject({ code: 'timeout' });
        await vi.advanceTimersByTimeAsync(5001);
        await assertion;
    });
});

describe('entrées utilisateur', () => {
    it.each(['https://api.example.org/base/', 'http://localhost:8000/'])(
        'normalise une adresse autorisée : %s',
        (value) => expect(normalizeApiUrl(value)).not.toMatch(/\/$/),
    );
    it.each([
        'example.org',
        'javascript:alert(1)',
        'http://remote.example.org',
        'https://user:pass@example.org',
        'https://example.org?token=x',
        'https://example.org#secret',
    ])('refuse une adresse inadaptée : %s', (value) =>
        expect(() => normalizeApiUrl(value)).toThrow(),
    );
    it('rejette SVG, fichier vide et capture trop volumineuse', () => {
        for (const file of [
            new File(['svg'], 'x.svg', { type: 'image/svg+xml' }),
            new File([], 'x.png', { type: 'image/png' }),
            new File([new Uint8Array(5 * 1024 * 1024 + 1)], 'x.png', { type: 'image/png' }),
        ]) {
            expect(() => validateFile(file)).toThrow();
        }
    });
});
