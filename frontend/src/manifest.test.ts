import { readFileSync, existsSync } from 'node:fs';
import { expect, it } from 'vitest';

it('déclare une extension MV3 sans accès aux onglets ni moteur de modèle embarqué', () => {
    const manifest = JSON.parse(
        readFileSync(new URL('../public/manifest.json', import.meta.url), 'utf8'),
    );
    expect(manifest.manifest_version).toBe(3);
    expect(manifest.permissions).toEqual(['storage']);
    expect(manifest.host_permissions).toEqual(['http://127.0.0.1/*', 'http://localhost/*']);
    expect(manifest.optional_host_permissions).toEqual(['https://*/*']);
    expect(manifest.content_scripts).toBeUndefined();
    expect(existsSync(new URL('../index.html', import.meta.url))).toBe(true);
    expect(manifest.content_security_policy.extension_pages).not.toContain('unsafe-eval');
    const validator = readFileSync(
        new URL('./generated/perception-validator.js', import.meta.url),
        'utf8',
    );
    expect(validator).not.toMatch(/new Function\s*\(|\beval\s*\(|\brequire\s*\(/);
});
