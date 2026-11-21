import { requestJson } from './api';
import {
    activeContext,
    captureActiveTab,
    imagePointToViewport,
    sameContext,
    type TabCapture,
} from './tab-capture';
import validateFrame from '../generated/vision-frame-validator.js';

type Box = { x: number; y: number; width: number; height: number };
type Control = 'club' | 'players' | 'previous' | 'next';
export type VisionFrame = {
    source: 'vision';
    capture_id: string;
    model_name: string;
    image: { width: number; height: number };
    scene: 'players' | 'club' | 'other';
    screen_hash: string;
    image_sha256: string;
    list_bbox: Box | null;
    controls: Partial<Record<Control, Box>>;
    rows: Array<{ element_id: string; bbox: Box; detector: string }>;
    ocr?: {
        cards: Array<{
            reading: { name: string; rating: number } | null;
            issues: string[];
            candidate_ids: number[];
        }>;
    } | null;
};
export type VisionReport = {
    source: 'vision';
    captures: number;
    readings: number;
    identified: number;
    uncertain: number;
    complete: boolean;
    inventory_updated: false;
};

// Actionneur générique : aucun nom, attribut de joueur, sélecteur ou HTML n'est lu.
export function visionPointInTab(command: {
    type: 'click' | 'scroll';
    x: number;
    y: number;
    amount: number;
}) {
    if (
        !['ea.com', 'www.ea.com'].includes(location.hostname) ||
        !location.pathname.includes('/ultimate-team/web-app/')
    )
        throw new Error('Ouvrir la Web App EA.');
    const { type, x, y, amount } = command;
    if (
        ![x, y, amount].every(Number.isFinite) ||
        x < 0 ||
        y < 0 ||
        x >= innerWidth ||
        y >= innerHeight ||
        Math.abs(amount) > 100000
    )
        throw new Error('Coordonnées vision invalides.');
    const target = document.elementFromPoint(x, y);
    if (!target) throw new Error('Point visuel inaccessible.');
    if (type === 'scroll') {
        let node: Element | null = target;
        while (node && node.scrollHeight <= node.clientHeight + 2) node = node.parentElement;
        if (node) node.scrollBy({ top: amount, behavior: 'instant' });
        else window.scrollBy({ top: amount, behavior: 'instant' });
    } else if (type === 'click') {
        for (const event of ['mousedown', 'mouseup', 'click'])
            target.dispatchEvent(
                new MouseEvent(event, { bubbles: true, button: 0, clientX: x, clientY: y }),
            );
    } else throw new Error('Action vision inconnue.');
    return true;
}

async function pixelHash(capture: TabCapture, box: Box) {
    const bitmap = await createImageBitmap(capture.file),
        canvas = new OffscreenCanvas(64, 96),
        context = canvas.getContext('2d')!;
    context.drawImage(bitmap, box.x, box.y, box.width, box.height, 0, 0, 64, 96);
    bitmap.close();
    const bytes = context.getImageData(0, 0, 64, 96).data;
    for (let i = 0; i < bytes.length; i++) bytes[i] = Math.floor(bytes[i] / 16) * 16;
    return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)))
        .map((x) => x.toString(16).padStart(2, '0'))
        .join('');
}

export async function scanVision(
    base: string,
    signal: AbortSignal,
    progress: (message: string) => void,
    maxFrames = 120,
): Promise<VisionReport> {
    if (!Number.isInteger(maxFrames) || maxFrames < 3 || maxFrames > 500)
        throw new Error('Le parcours vision demande entre 3 et 500 captures.');
    const initial = await activeContext(signal),
        captureIds: string[] = [],
        actions: Array<{ capture_id: string; action: Control | 'up' | 'down' }> = [];
    let capture: TabCapture | undefined,
        frame: VisionFrame | undefined,
        complete = false;
    const release = () => {
        if (capture) URL.revokeObjectURL(capture.url);
        capture = undefined;
    };
    async function observe() {
        release();
        signal.throwIfAborted();
        if (captureIds.length >= maxFrames) return false;
        const context = await activeContext(signal);
        if (
            context.tabId !== initial.tabId ||
            context.documentId !== initial.documentId ||
            context.viewport.href !== initial.viewport.href
        )
            throw new Error('L’onglet a changé ; arrêt du scan vision.');
        capture = await captureActiveTab(signal);
        const id = crypto.randomUUID();
        const result = await requestJson(
            base,
            `/api/v1/perception/club-analyze?capture_id=${id}`,
            { method: 'POST', headers: { 'Content-Type': 'image/png' }, body: capture.file },
            signal,
            25000,
        );
        if (!validateFrame(result)) throw new Error('Observation vision non conforme.');
        frame = result as VisionFrame;
        if (
            frame.capture_id !== id ||
            frame.image.width !== capture.width ||
            frame.image.height !== capture.height ||
            !sameContext(capture.context, context)
        )
            throw new Error('La réponse vision ne correspond pas à la capture.');
        captureIds.push(id);
        progress(
            `Vision uniquement : ${captureIds.length} captures analysées ; lecture des cartes visibles…`,
        );
        return true;
    }
    async function act(action: Control | 'up' | 'down') {
        if (!frame || !capture) throw new Error('Capture absente.');
        const scroll = action === 'up' || action === 'down',
            box = scroll ? frame.list_bbox : frame.controls[action];
        if (!box) throw new Error('Commande non reconnue dans les pixels.');
        if (!scroll) {
            // Revoir l'image avant chaque clic : aucune action si l'interface a changé.
            const area = frame.list_bbox ?? {
                    x: 0,
                    y: 0,
                    width: capture.width,
                    height: capture.height,
                },
                before = await pixelHash(capture, area),
                button = await pixelHash(capture, box),
                fresh = await captureActiveTab(signal);
            try {
                if (
                    fresh.width !== capture.width ||
                    fresh.height !== capture.height ||
                    (await pixelHash(fresh, area)) !== before ||
                    (await pixelHash(fresh, box)) !== button
                )
                    throw new Error('L’image a changé avant le clic vision.');
            } finally {
                URL.revokeObjectURL(fresh.url);
            }
        }
        const point = imagePointToViewport(capture, box),
            context = await activeContext(signal);
        if (!sameContext(context, capture.context)) throw new Error('L’onglet a changé.');
        signal.throwIfAborted();
        const results = await chrome.scripting.executeScript({
            target: { tabId: initial.tabId, documentIds: [initial.documentId] },
            func: visionPointInTab,
            args: [
                {
                    type: scroll ? 'scroll' : 'click',
                    ...point,
                    amount: action === 'up' ? -100000 : context.viewport.height * 0.38,
                },
            ],
        });
        if (!results.some((r) => r.frameId === 0 && r.result === true))
            throw new Error('L’action vision n’a pas été confirmée.');
        actions.push({ capture_id: frame.capture_id, action });
        await new Promise((resolve) => setTimeout(resolve, 350));
        signal.throwIfAborted();
    }
    try {
        await observe();
        for (let i = 0; frame?.scene !== 'players' && i < 3; i++) {
            const control =
                frame?.scene === 'club' && frame.controls.players
                    ? 'players'
                    : frame?.scene === 'other' && frame.controls.club
                      ? 'club'
                      : null;
            if (!control)
                throw new Error(
                    'Ouvrir « Club → Players » : la vision ne reconnaît pas cet écran.',
                );
            await act(control);
            await observe();
        }
        if (frame?.scene !== 'players') throw new Error('La liste du club n’est pas reconnue.');
        let previousPages = 0;
        while (frame.controls.previous && previousPages++ < 50) {
            await act('previous');
            if (!(await observe())) break;
        }
        if (frame.controls.previous)
            throw new Error('La vision n’a pas pu revenir à la première page.');
        await act('up');
        await observe();
        while (captureIds.length < maxFrames && frame?.scene === 'players') {
            const before = frame.screen_hash;
            await act('down');
            if (!(await observe())) break;
            if (frame.screen_hash !== before) continue;
            if (!frame.controls.next) {
                complete = true;
                break;
            }
            await act('next');
            if (!(await observe())) break;
            await act('up');
            if (!(await observe())) break;
        }
        const result = (await requestJson(
            base,
            '/api/v1/sbc/vision-scan',
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ capture_ids: captureIds, actions, complete }),
            },
            signal,
            15000,
        )) as VisionReport;
        if (
            result.source !== 'vision' ||
            result.inventory_updated !== false ||
            result.captures !== captureIds.length
        )
            throw new Error('Le relevé vision n’a pas pu être vérifié.');
        return result;
    } finally {
        release();
    }
}
