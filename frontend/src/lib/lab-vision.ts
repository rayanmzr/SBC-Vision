import type { Perception } from './api';

// Protocole visuel volontairement limité au laboratoire, sans OCR ni modèle entraîné.
export const LAB_COLORS = [
    { id: 'lab-select', text: 'Sélectionner la carte fictive', rgb: [24, 122, 211] },
    { id: 'lab-place', text: 'Placer la carte fictive', rgb: [142, 65, 198] },
    { id: 'lab-done', text: 'Carte fictive placée', rgb: [20, 160, 110] },
] as const;

export function perceiveLabPixels(
    pixels: { width: number; height: number; data: Uint8ClampedArray },
    captureId: string,
): Perception {
    const { width, height, data } = pixels;
    if (
        !Number.isInteger(width) ||
        !Number.isInteger(height) ||
        width <= 0 ||
        height <= 0 ||
        width * height > 20_000_000 ||
        data.length !== width * height * 4
    )
        throw new Error('Image de laboratoire invalide.');
    const elements: Perception['elements'] = [];
    for (const marker of LAB_COLORS) {
        let left = width,
            top = height,
            right = -1,
            bottom = -1,
            count = 0;
        for (let y = 0; y < height; y++)
            for (let x = 0; x < width; x++) {
                const i = (y * width + x) * 4;
                if (
                    data[i + 3] >= 250 &&
                    marker.rgb.every((channel, k) => Math.abs(data[i + k] - channel) <= 3)
                ) {
                    left = Math.min(left, x);
                    top = Math.min(top, y);
                    right = Math.max(right, x);
                    bottom = Math.max(bottom, y);
                    count++;
                }
            }
        if (!count) continue;
        const w = right - left + 1,
            h = bottom - top + 1;
        if (w < 24 || h < 20 || count / (w * h) < 0.98)
            throw new Error('Repère coloré incomplet, masqué ou ambigu.');
        elements.push({
            id: marker.id,
            text: marker.text,
            kind: marker.id === 'lab-done' ? 'text' : 'button',
            bbox: { x: left, y: top, width: w, height: h },
            confidence: 1,
            actions: marker.id === 'lab-done' ? [] : ['click'],
        });
    }
    if (elements.length !== 1)
        throw new Error('Un seul état coloré du laboratoire doit être visible.');
    return {
        schema_version: '0.1',
        model_name: 'local-color-baseline-v1',
        capture_id: captureId,
        image: { width, height },
        elements,
    };
}

export async function perceiveLabImage(image: Blob, signal: AbortSignal): Promise<Perception> {
    signal.throwIfAborted();
    const bitmap = await createImageBitmap(image);
    try {
        signal.throwIfAborted();
        if (bitmap.width * bitmap.height > 20_000_000) throw new Error('Image trop grande.');
        const canvas = document.createElement('canvas');
        canvas.width = bitmap.width;
        canvas.height = bitmap.height;
        const context = canvas.getContext('2d', { willReadFrequently: true });
        if (!context) throw new Error('Lecture des pixels indisponible.');
        context.drawImage(bitmap, 0, 0);
        const result = perceiveLabPixels(
            context.getImageData(0, 0, canvas.width, canvas.height),
            crypto.randomUUID(),
        );
        signal.throwIfAborted();
        return result;
    } finally {
        bitmap.close();
    }
}
