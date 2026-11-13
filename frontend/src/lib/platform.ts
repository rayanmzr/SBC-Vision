export const DEFAULT_API_URL = 'http://127.0.0.1:8000';
const STORAGE_KEY = 'apiUrl';

export function isExtension(): boolean {
    return typeof chrome !== 'undefined' && Boolean(chrome.runtime?.id);
}

export function normalizeApiUrl(value: string): string {
    let url: URL;
    try {
        url = new URL(value.trim());
    } catch {
        throw new Error('Saisis une adresse complète, par exemple http://127.0.0.1:8000.');
    }
    const local = ['127.0.0.1', 'localhost'].includes(url.hostname);
    if (url.protocol !== 'https:' && !(url.protocol === 'http:' && local)) {
        throw new Error('Utilise HTTPS pour une API distante, ou HTTP sur localhost / 127.0.0.1.');
    }
    if (url.username || url.password || url.search || url.hash) {
        throw new Error(
            'L’adresse API ne doit contenir ni identifiants, ni paramètres, ni fragment.',
        );
    }
    return url.href.replace(/\/+$/, '');
}

export async function loadApiUrl(): Promise<string> {
    const value = isExtension()
        ? (await chrome.storage.local.get(STORAGE_KEY))[STORAGE_KEY]
        : localStorage.getItem(STORAGE_KEY);
    return typeof value === 'string' ? normalizeApiUrl(value) : DEFAULT_API_URL;
}

export async function saveApiUrl(url: string): Promise<void> {
    if (isExtension()) await chrome.storage.local.set({ [STORAGE_KEY]: url });
    else localStorage.setItem(STORAGE_KEY, url);
}

export async function authorizeApi(url: string): Promise<void> {
    const parsed = new URL(url);
    if (!isExtension()) {
        if (url !== DEFAULT_API_URL) {
            throw new Error(
                'L’aperçu web utilise http://127.0.0.1:8000. Installe l’extension pour une autre API.',
            );
        }
        return;
    }
    if (parsed.protocol === 'https:') {
        // Appel depuis le clic « Vérifier la connexion », avant toute autre attente.
        const granted = await chrome.permissions.request({
            origins: [`https://${parsed.hostname}/*`],
        });
        if (!granted)
            throw new Error('L’accès à cette API a été refusé. Aucune requête n’a été envoyée.');
    }
}

export function requestUrl(base: string, path: string): string {
    if (!isExtension()) {
        if (base !== DEFAULT_API_URL) throw new Error('Cette API nécessite l’extension installée.');
        return `/__api${path}`;
    }
    return `${base}${path}`;
}

export async function openWorkspace(): Promise<void> {
    await chrome.tabs.create({ url: chrome.runtime.getURL('index.html') });
}
