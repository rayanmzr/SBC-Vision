import { afterEach, expect, it, vi } from 'vitest';
import { clearSessionApiKey, sessionApiHeaders, setSessionApiKey } from './api-key';
import { requestJson } from './api';
import { DEFAULT_API_URL } from './platform';

const KEY = 'local_test_key_' + 'x'.repeat(32);
afterEach(() => {
    clearSessionApiKey();
    vi.unstubAllGlobals();
});

it('attache la clé à une adresse exacte en mémoire et la supprime explicitement', () => {
    setSessionApiKey(DEFAULT_API_URL, KEY);
    expect(sessionApiHeaders(DEFAULT_API_URL)).toEqual({ Authorization: `Bearer ${KEY}` });
    expect(sessionApiHeaders('https://other.example')).toEqual({});
    expect(sessionApiHeaders(`${DEFAULT_API_URL}/other`)).toEqual({});
    clearSessionApiKey();
    expect(sessionApiHeaders(DEFAULT_API_URL)).toEqual({});
});
it('remplace la session au lieu de conserver des clés pour plusieurs hôtes', () => {
    setSessionApiKey(DEFAULT_API_URL, KEY);
    setSessionApiKey('https://example.test', KEY);
    expect(sessionApiHeaders(DEFAULT_API_URL)).toEqual({});
    setSessionApiKey('https://example.test', '');
    expect(sessionApiHeaders('https://example.test')).toEqual({});
});
it.each(['short', 'é'.repeat(40), 'x'.repeat(32) + '\n'])('refuse une clé invalide', (key) => {
    expect(() => setSessionApiKey(DEFAULT_API_URL, key)).toThrow();
});
it('envoie la clé dans Authorization, jamais dans l’URL ou le corps', async () => {
    const fetchMock = vi.fn(async () => new Response('{}'));
    vi.stubGlobal('fetch', fetchMock);
    setSessionApiKey(DEFAULT_API_URL, KEY);
    await requestJson(
        DEFAULT_API_URL,
        '/api/v1/sbc/workspace',
        {},
        new AbortController().signal,
        1000,
    );
    const [url, options] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).not.toContain(KEY);
    expect(options.body).toBeUndefined();
    expect(new Headers(options.headers).get('Authorization')).toBe(`Bearer ${KEY}`);
    expect(options.credentials).toBe('omit');
    expect(options.redirect).toBe('error');
});
it('ne transmet pas une clé à une API différente', async () => {
    vi.stubGlobal('chrome', { runtime: { id: 'test-extension' } });
    const fetchMock = vi.fn(async () => new Response('{}'));
    vi.stubGlobal('fetch', fetchMock);
    setSessionApiKey(DEFAULT_API_URL, KEY);
    await requestJson('https://other.example', '/health', {}, new AbortController().signal, 1000);
    const [, options] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(new Headers(options.headers).has('Authorization')).toBe(false);
});
