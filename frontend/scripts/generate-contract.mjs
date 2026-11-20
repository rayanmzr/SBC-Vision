// Compiler le schéma partagé au build : aucun eval n'est nécessaire dans l'extension MV3.
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import Ajv from 'ajv/dist/2020.js';
import standalone from 'ajv/dist/standalone/index.js';

for (const [contract, output] of [
    ['perception.schema.json', 'perception-validator.js'],
    ['sbc-report.schema.json', 'sbc-report-validator.js'],
    ['workspace.schema.json', 'workspace-validator.js'],
    ['solve-response.schema.json', 'solve-response-validator.js'],
]) {
    const schema = JSON.parse(
        await readFile(new URL(`../../contracts/${contract}`, import.meta.url)),
    );
    const ajv = new Ajv({ code: { source: true, esm: true }, unicode: false, allErrors: true });
    const code =
        `// Généré depuis contracts/${contract} ; pnpm schema pour actualiser.\n` +
        standalone(ajv, ajv.compile(schema)) +
        '\n';
    const target = new URL(`../src/generated/${output}`, import.meta.url);
    if (/\brequire\s*\(|new Function\s*\(|\beval\s*\(/.test(code)) {
        throw new Error('Le validateur doit rester compatible avec la CSP de Manifest V3.');
    }
    if (process.argv.includes('--check')) {
        if ((await readFile(target, 'utf8').catch(() => '')) !== code) {
            throw new Error(`Contrat ${contract} périmé : exécuter pnpm schema.`);
        }
        console.log(`Contrat ${contract} à jour.`);
    } else {
        await mkdir(new URL('../src/generated/', import.meta.url), { recursive: true });
        await writeFile(target, code);
        console.log(`Validateur ${contract} généré.`);
    }
}
