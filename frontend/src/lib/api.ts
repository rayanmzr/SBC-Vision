import validateSchema from '../generated/perception-validator.js';
import { requestUrl } from './platform';

export type ElementKind =
    'button' | 'input' | 'link' | 'menu' | 'checkbox' | 'card' | 'slot' | 'text';
export type ActionKind = 'click' | 'fill' | 'select' | 'scroll';
export interface Perception {
    schema_version: '0.1';
    capture_id: string;
    model_name: string;
    image: { width: number; height: number };
    elements: Array<{
        id: string;
        kind: ElementKind;
        bbox: { x: number; y: number; width: number; height: number };
        text?: string | null;
        confidence: number;
        actions?: ActionKind[];
    }>;
}
export interface Connection {
    version: string;
    modelLoaded: boolean;
    perception: boolean;
    ocr: boolean;
}

export class ApiError extends Error {
    constructor(
        message: string,
        public code: string,
        public status?: number,
    ) {
        super(message);
    }
}

export function validatePerception(
    value: unknown,
    expected?: { captureId: string; width: number; height: number },
): Perception {
    const invalid = () =>
        new ApiError('Le JSON reçu ne respecte pas le contrat de perception.', 'invalid_response');
    if (!validateSchema(value)) throw invalid();
    const result = value as Perception;
    const ids = new Set<string>();
    for (const element of result.elements) {
        const { bbox, actions = [] } = element;
        if (
            ids.has(element.id) ||
            new Set(actions).size !== actions.length ||
            bbox.x + bbox.width > result.image.width ||
            bbox.y + bbox.height > result.image.height
        ) {
            throw invalid();
        }
        ids.add(element.id);
    }
    if (
        expected &&
        (result.capture_id !== expected.captureId ||
            result.image.width !== expected.width ||
            result.image.height !== expected.height)
    ) {
        throw new ApiError(
            'La réponse correspond à une autre capture ou à d’autres dimensions.',
            'capture_mismatch',
        );
    }
    return result;
}

export async function requestJson(
    base: string,
    path: string,
    options: RequestInit,
    signal: AbortSignal,
    timeout: number,
): Promise<unknown> {
    const timer = new AbortController();
    const combined = AbortSignal.any([signal, timer.signal]);
    const timeoutId = setTimeout(() => timer.abort(), timeout);
    try {
        const response = await fetch(requestUrl(base, path), {
            ...options,
            signal: combined,
            credentials: 'omit',
            redirect: 'error',
        });
        const text = await response.text();
        let body: unknown;
        try {
            body = JSON.parse(text);
        } catch {
            throw new ApiError(
                'Le serveur n’a pas renvoyé de JSON. Vérifie l’adresse de l’API et son démarrage.',
                'invalid_response',
                response.status,
            );
        }
        if (!response.ok) {
            const detail = (body as { detail?: { code?: unknown; message?: unknown } } | null)
                ?.detail;
            const code = typeof detail?.code === 'string' ? detail.code : 'http_error';
            const message =
                typeof detail?.message === 'string'
                    ? detail.message.slice(0, 300)
                    : `La requête a échoué (HTTP ${response.status}).`;
            throw new ApiError(message, code, response.status);
        }
        return body;
    } catch (error) {
        if (signal.aborted) throw new ApiError('L’opération a été annulée.', 'cancelled');
        if (timer.signal.aborted)
            throw new ApiError('L’API n’a pas répondu dans le délai prévu.', 'timeout');
        if (error instanceof ApiError) throw error;
        throw new ApiError(
            'Impossible de joindre l’API. Vérifie son adresse et que le serveur est démarré.',
            'network_error',
        );
    } finally {
        clearTimeout(timeoutId);
    }
}

export async function checkConnection(base: string, signal: AbortSignal): Promise<Connection> {
    const [health, capabilities] = await Promise.all([
        requestJson(base, '/health', {}, signal, 5000),
        requestJson(base, '/api/v1/capabilities', {}, signal, 5000),
    ]);
    const h = health as Record<string, unknown> | null;
    const c = capabilities as Record<string, unknown> | null;
    if (
        !h ||
        h.status !== 'ok' ||
        typeof h.version !== 'string' ||
        typeof h.model_loaded !== 'boolean' ||
        !c ||
        typeof c.perception !== 'boolean' ||
        typeof c.ocr !== 'boolean'
    ) {
        throw new ApiError(
            'Les routes de santé ne correspondent pas à l’API SBC Vision.',
            'invalid_response',
        );
    }
    return {
        version: h.version,
        modelLoaded: h.model_loaded,
        perception: c.perception,
        ocr: c.ocr,
    };
}

export async function analyzeImage(
    base: string,
    file: File,
    image: { width: number; height: number },
    signal: AbortSignal,
): Promise<Perception> {
    const captureId = crypto.randomUUID();
    const result = await requestJson(
        base,
        `/api/v1/perception/analyze?capture_id=${captureId}`,
        {
            method: 'POST',
            headers: { 'Content-Type': file.type },
            body: file,
        },
        signal,
        30_000,
    );
    return validatePerception(result, { captureId, ...image });
}

export function validateFile(file: File): void {
    if (!['image/png', 'image/jpeg'].includes(file.type))
        throw new Error('Choisis une image PNG ou JPEG.');
    if (!file.size) throw new Error('Cette image est vide.');
    if (file.size > 5 * 1024 * 1024) throw new Error('L’image doit peser au maximum 5 Mio.');
}

export async function readImage(
    file: File,
): Promise<{ url: string; width: number; height: number }> {
    validateFile(file);
    const url = URL.createObjectURL(file);
    try {
        const image = new Image();
        image.src = url;
        await image.decode();
        const width = image.naturalWidth,
            height = image.naturalHeight;
        if (!width || !height || Math.max(width, height) > 8192 || width * height > 20_000_000) {
            throw new Error(
                'Image trop grande : 8 192 pixels par côté et 20 millions de pixels au maximum.',
            );
        }
        return { url, width, height };
    } catch (error) {
        URL.revokeObjectURL(url);
        if (error instanceof Error && error.message.startsWith('Image trop grande')) throw error;
        throw new Error(
            'Impossible de lire cette image. Vérifie que le fichier PNG ou JPEG est intact.',
        );
    }
}
