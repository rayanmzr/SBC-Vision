import { expect, it } from 'vitest';
import { LAB_COLORS, perceiveLabPixels } from './lab-vision';

function image() {
    return { width: 180, height: 100, data: new Uint8ClampedArray(180 * 100 * 4) };
}
function rect(pixels: ReturnType<typeof image>, stage: number, x = 10, y = 20) {
    for (let row = y; row < y + 24; row++)
        for (let col = x; col < x + 40; col++) {
            const i = (row * pixels.width + col) * 4;
            pixels.data.set([...LAB_COLORS[stage].rgb, 255], i);
        }
}
it.each([0, 1, 2])('localise l’état %s dans les pixels, indépendamment de la position', (stage) => {
    const pixels = image();
    rect(pixels, stage, 75, 40);
    const result = perceiveLabPixels(pixels, 'capture-1');
    expect(result.elements[0]).toMatchObject({
        id: LAB_COLORS[stage].id,
        bbox: { x: 75, y: 40, width: 40, height: 24 },
    });
    expect(result.elements[0].actions).toEqual(stage === 2 ? [] : ['click']);
    expect(result.model_name).toBe('local-color-baseline-v1');
});
it('rejette les images sans repère, les états simultanés et les repères masqués', () => {
    expect(() => perceiveLabPixels(image(), 'empty')).toThrow('Un seul');
    const multiple = image();
    rect(multiple, 0);
    rect(multiple, 1, 80);
    expect(() => perceiveLabPixels(multiple, 'multiple')).toThrow('Un seul');
    const masked = image();
    rect(masked, 0);
    for (let y = 25; y < 35; y++) masked.data.fill(0, (y * 180 + 20) * 4, (y * 180 + 40) * 4);
    expect(() => perceiveLabPixels(masked, 'masked')).toThrow('masqué');
    const duplicate = image();
    rect(duplicate, 0);
    rect(duplicate, 0, 100);
    expect(() => perceiveLabPixels(duplicate, 'duplicate')).toThrow('ambigu');
});
it('refuse des dimensions ou une charge de pixels incohérentes', () => {
    expect(() =>
        perceiveLabPixels({ width: 180, height: 100, data: new Uint8ClampedArray(4) }, 'bad'),
    ).toThrow('invalide');
});
