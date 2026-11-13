import { readImage } from './api';
import { isExtension } from './platform';

export type Viewport = {
    href: string;
    width: number;
    height: number;
    scrollX: number;
    scrollY: number;
    pixelRatio: number;
    visualScale: number;
    offsetX: number;
    offsetY: number;
    timeOrigin: number;
    visibility: string;
};
export type TabContext = {
    tabId: number;
    windowId: number;
    documentId: string;
    viewport: Viewport;
};
export type TabCapture = {
    file: File;
    url: string;
    width: number;
    height: number;
    context: TabContext;
    capturedAt: string;
};

let capturing = false;
let lastAttempt = -Infinity;
const MIN_CAPTURE_INTERVAL = 600;

// Cadre principal uniquement : géométrie, sans texte ni sélecteur de l’interface.
function viewportInPage(): Viewport {
    return {
        href: location.href,
        width: window.innerWidth,
        height: window.innerHeight,
        scrollX: window.scrollX,
        scrollY: window.scrollY,
        pixelRatio: window.devicePixelRatio,
        visualScale: window.visualViewport?.scale ?? 1,
        offsetX: window.visualViewport?.offsetLeft ?? 0,
        offsetY: window.visualViewport?.offsetTop ?? 0,
        timeOrigin: performance.timeOrigin,
        visibility: document.visibilityState,
    };
}

export function validateViewport(value: unknown): Viewport {
    const v = value as Viewport | null;
    if (
        !v ||
        typeof v.href !== 'string' ||
        !['http:', 'https:'].includes(new URL(v.href).protocol) ||
        !Number.isInteger(v.width) ||
        !Number.isInteger(v.height) ||
        v.width <= 0 ||
        v.height <= 0 ||
        ![
            v.scrollX,
            v.scrollY,
            v.pixelRatio,
            v.visualScale,
            v.offsetX,
            v.offsetY,
            v.timeOrigin,
        ].every(Number.isFinite) ||
        v.pixelRatio <= 0 ||
        v.timeOrigin <= 0 ||
        v.visibility !== 'visible'
    )
        throw new Error('La géométrie de l’onglet ne peut pas être confirmée.');
    if (
        Math.abs(v.visualScale - 1) > 0.001 ||
        Math.abs(v.offsetX) > 0.01 ||
        Math.abs(v.offsetY) > 0.01
    )
        throw new Error('Revenir au zoom tactile normal avant de capturer cet onglet.');
    return v;
}

export function sameContext(a: TabContext, b: TabContext): boolean {
    return (
        a.tabId === b.tabId &&
        a.windowId === b.windowId &&
        a.documentId === b.documentId &&
        (Object.keys(a.viewport) as Array<keyof Viewport>).every(
            (key) => a.viewport[key] === b.viewport[key],
        )
    );
}

async function activeContext(signal: AbortSignal): Promise<TabContext> {
    signal.throwIfAborted();
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    signal.throwIfAborted();
    if (tab?.id == null || tab.windowId == null || !tab.url || !/^https?:\/\//.test(tab.url))
        throw new Error(
            'Ouvrir une page HTTP ou HTTPS, puis cliquer l’icône SBC Vision sur cette page.',
        );
    if (tab.status !== 'complete') throw new Error('Attendre la fin du chargement de l’onglet.');
    const results = await chrome.scripting.executeScript({
        target: { tabId: tab.id, frameIds: [0] },
        func: viewportInPage,
    });
    signal.throwIfAborted();
    const result = results.find((entry) => entry.frameId === 0);
    if (!result?.documentId)
        throw new Error('Le document de cet onglet ne peut pas être identifié.');
    const viewport = validateViewport(result.result);
    if (viewport.href !== tab.url)
        throw new Error('L’onglet a changé pendant la lecture. Refaire une capture.');
    return { tabId: tab.id, windowId: tab.windowId, documentId: result.documentId, viewport };
}

function waitForCaptureSlot(signal: AbortSignal): Promise<void> {
    signal.throwIfAborted();
    const delay = Math.max(0, MIN_CAPTURE_INTERVAL - (performance.now() - lastAttempt));
    return new Promise((resolve, reject) => {
        const abort = () => {
            clearTimeout(timer);
            reject(signal.reason);
        };
        const timer = setTimeout(() => {
            signal.removeEventListener('abort', abort);
            resolve();
        }, delay);
        signal.addEventListener('abort', abort, { once: true });
    });
}

export function validateCaptureSize(image: { width: number; height: number }, viewport: Viewport) {
    // La capture et le viewport doivent partager le même facteur d’échelle, à l’arrondi près.
    const scale = image.width / viewport.width;
    if (
        !Number.isSafeInteger(image.width) ||
        !Number.isSafeInteger(image.height) ||
        image.width <= 0 ||
        image.height <= 0 ||
        !Number.isFinite(scale) ||
        scale <= 0 ||
        Math.abs(image.height - viewport.height * scale) > 2
    )
        throw new Error(
            'Les dimensions de la capture ne correspondent pas au viewport de l’onglet.',
        );
}

export async function captureActiveTab(signal: AbortSignal): Promise<TabCapture> {
    if (!isExtension())
        throw new Error('La capture d’onglet nécessite l’extension Chrome installée.');
    if (capturing) throw new Error('Une capture est déjà en cours.');
    capturing = true;
    let imageUrl: string | undefined;
    try {
        await waitForCaptureSlot(signal);
        const before = await activeContext(signal);
        signal.throwIfAborted();
        lastAttempt = performance.now();
        const dataUrl = await chrome.tabs.captureVisibleTab(before.windowId, { format: 'png' });
        signal.throwIfAborted();
        const after = await activeContext(signal);
        if (!sameContext(before, after))
            throw new Error(
                'L’onglet, le défilement ou la taille a changé pendant la capture. Recommencer.',
            );
        if (!dataUrl.startsWith('data:image/png;base64,') || dataUrl.length > 7_000_000)
            throw new Error('La capture PNG est invalide ou trop volumineuse. Réduire la fenêtre.');
        const encoded = dataUrl.slice('data:image/png;base64,'.length);
        const bytes = Uint8Array.from(atob(encoded), (char) => char.charCodeAt(0));
        const file = new File([bytes], 'capture-onglet.png', { type: 'image/png' });
        const image = await readImage(file);
        imageUrl = image.url;
        signal.throwIfAborted();
        validateCaptureSize(image, before.viewport);
        return { file, ...image, context: before, capturedAt: new Date().toISOString() };
    } catch (error) {
        if (imageUrl) URL.revokeObjectURL(imageUrl);
        if (signal.aborted) throw new Error('La capture a été annulée.');
        if (error instanceof Error) throw error;
        throw new Error(
            'Capture refusée par Chrome. Rouvrir l’extension depuis l’onglet à observer.',
        );
    } finally {
        capturing = false;
    }
}

export function imagePointToViewport(
    capture: Pick<TabCapture, 'width' | 'height' | 'context'>,
    box: { x: number; y: number; width: number; height: number },
): { x: number; y: number } {
    validateViewport(capture.context.viewport);
    validateCaptureSize(capture, capture.context.viewport);
    if (
        ![box.x, box.y, box.width, box.height].every(Number.isFinite) ||
        box.x < 0 ||
        box.y < 0 ||
        box.width <= 0 ||
        box.height <= 0 ||
        box.x + box.width > capture.width ||
        box.y + box.height > capture.height
    )
        throw new Error('La boîte est hors de la capture.');
    return {
        x: ((box.x + box.width / 2) * capture.context.viewport.width) / capture.width,
        y: ((box.y + box.height / 2) * capture.context.viewport.height) / capture.height,
    };
}
