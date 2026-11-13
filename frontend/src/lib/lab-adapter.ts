import { captureActiveTab, activeContext, sameContext, type Viewport } from './tab-capture';
import { perceiveLabImage } from './lab-vision';
import { planLocalAction, type ControllerAdapter, type Frame, type Action } from './controller';

export function isLocalLabUrl(value: string): boolean {
    try {
        const url = new URL(value);
        return (
            url.protocol === 'http:' &&
            ['127.0.0.1', 'localhost'].includes(url.hostname) &&
            ['5173', '4173'].includes(url.port) &&
            url.pathname === '/controller-lab.html' &&
            !url.search &&
            !url.hash &&
            !url.username &&
            !url.password
        );
    } catch {
        return false;
    }
}

// Appelée dans le document précis de la capture. Aucun texte du DOM n’est lu pour choisir l’action.
function clickInLab(x: number, y: number, expected: Viewport, expiresAt: number) {
    const url = new URL(location.href);
    if (
        url.protocol !== 'http:' ||
        !['127.0.0.1', 'localhost'].includes(url.hostname) ||
        !['5173', '4173'].includes(url.port) ||
        url.pathname !== '/controller-lab.html' ||
        url.search ||
        url.hash ||
        url.username ||
        url.password ||
        location.href !== expected.href ||
        performance.timeOrigin !== expected.timeOrigin ||
        Date.now() > expiresAt ||
        document.visibilityState !== 'visible' ||
        innerWidth !== expected.width ||
        innerHeight !== expected.height ||
        scrollX !== expected.scrollX ||
        scrollY !== expected.scrollY ||
        devicePixelRatio !== expected.pixelRatio ||
        (visualViewport?.scale ?? 1) !== expected.visualScale ||
        (visualViewport?.offsetLeft ?? 0) !== expected.offsetX ||
        (visualViewport?.offsetTop ?? 0) !== expected.offsetY ||
        !Number.isFinite(x) ||
        !Number.isFinite(y) ||
        x < 0 ||
        y < 0 ||
        x >= innerWidth ||
        y >= innerHeight
    )
        throw new Error('Contexte local différent ou commande périmée.');
    const target = document.elementFromPoint(x, y);
    if (!(target instanceof HTMLCanvasElement) || target.dataset.sbcControllerLab !== 'v1')
        throw new Error('Le point ne désigne pas le canevas du laboratoire.');
    target.dispatchEvent(new MouseEvent('click', { clientX: x, clientY: y, bubbles: true }));
    return true;
}

export function nativeLabAdapter(): ControllerAdapter {
    return {
        observe: async (signal) => {
            const allowed = await activeContext(signal);
            if (!isLocalLabUrl(allowed.viewport.href))
                throw new Error(
                    'Ouvrir la page locale controller-lab.html sur le port 5173 ou 4173.',
                );
            const capture = await captureActiveTab(signal);
            try {
                if (!sameContext(allowed, capture.context)) throw new Error('L’onglet a changé.');
                const perception = await perceiveLabImage(capture.file, signal);
                return {
                    geometry: {
                        width: capture.width,
                        height: capture.height,
                        context: capture.context,
                    },
                    target: `${capture.context.tabId}:${capture.context.documentId}`,
                    perception,
                    observedAt: Date.now(),
                };
            } finally {
                URL.revokeObjectURL(capture.url);
            }
        },
        click: async (frame, action, signal) => {
            assertAction(frame, action);
            if (!isLocalLabUrl(frame.geometry.context.viewport.href))
                throw new Error('Cible hors laboratoire.');
            const current = await activeContext(signal);
            if (!sameContext(current, frame.geometry.context))
                throw new Error('Contexte modifié avant le clic.');
            signal.throwIfAborted();
            const result = await chrome.scripting.executeScript({
                target: { tabId: current.tabId, documentIds: [current.documentId] },
                func: clickInLab,
                args: [action.x, action.y, current.viewport, Date.now() + 1000],
            });
            signal.throwIfAborted();
            if (result.length !== 1 || result[0].result !== true)
                throw new Error('Envoi du clic non confirmé.');
        },
    };
}

function assertAction(frame: Frame, action: Action) {
    if (JSON.stringify(planLocalAction(frame)) !== JSON.stringify(action))
        throw new Error('Action différente du JSON observé.');
}

export function canvasLabAdapter(canvas: HTMLCanvasElement): ControllerAdapter {
    const context = () => ({
        tabId: 0,
        windowId: 0,
        documentId: String(performance.timeOrigin),
        viewport: {
            href: location.href,
            width: canvas.width,
            height: canvas.height,
            scrollX: 0,
            scrollY: 0,
            pixelRatio: 1,
            visualScale: 1,
            offsetX: 0,
            offsetY: 0,
            timeOrigin: performance.timeOrigin,
            visibility: 'visible',
        },
    });
    const target = () =>
        JSON.stringify({
            origin: location.href,
            rect: canvas.getBoundingClientRect().toJSON(),
            scrollX,
            scrollY,
            dpr: devicePixelRatio,
        });
    return {
        observe: async (signal) => {
            signal.throwIfAborted();
            const before = target();
            const image = await new Promise<Blob>((resolve, reject) =>
                canvas.toBlob(
                    (blob) =>
                        blob ? resolve(blob) : reject(new Error('Capture du canevas impossible.')),
                    'image/png',
                ),
            );
            const perception = await perceiveLabImage(image, signal);
            if (before !== target()) throw new Error('Le canevas a bougé pendant la capture.');
            return {
                geometry: { width: canvas.width, height: canvas.height, context: context() },
                target: before,
                perception,
                observedAt: Date.now(),
            };
        },
        click: async (frame, action, signal) => {
            signal.throwIfAborted();
            assertAction(frame, action);
            if (target() !== frame.target || !isLocalLabUrl(location.href))
                throw new Error('Canevas ou page modifié.');
            const rect = canvas.getBoundingClientRect();
            const x = rect.left + (action.x * rect.width) / canvas.width;
            const y = rect.top + (action.y * rect.height) / canvas.height;
            if (document.elementFromPoint(x, y) !== canvas)
                throw new Error('Le canevas est hors écran ou masqué.');
            canvas.dispatchEvent(
                new MouseEvent('click', { clientX: x, clientY: y, bubbles: true }),
            );
            // Laisser React redessiner avant la capture de vérification.
            await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
            signal.throwIfAborted();
        },
    };
}
