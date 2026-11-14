import { normalizeApiUrl } from './platform';

// Une seule clé en mémoire, attachée à une adresse exacte ; jamais dans storage.
let current: { base: string; key: string } | null = null;

export function setSessionApiKey(base: string, key: string) {
    if (!key) {
        current = null;
        return;
    }
    if (!/^[A-Za-z0-9_-]{32,256}$/.test(key))
        throw new Error('La clé API doit contenir 32 à 256 caractères alphanumériques, _ ou -.');
    current = { base: normalizeApiUrl(base), key };
}

export function clearSessionApiKey() {
    current = null;
}

export function sessionApiHeaders(base: string): Record<string, string> {
    return current?.base === base ? { Authorization: `Bearer ${current.key}` } : {};
}
