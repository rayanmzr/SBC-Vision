// Compiler le schéma partagé au build : aucun eval n'est nécessaire dans l'extension MV3.
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import Ajv from 'ajv/dist/2020.js';
import standalone from 'ajv/dist/standalone/index.js';

const schema = JSON.parse(
    await readFile(new URL('../../contracts/perception.schema.json', import.meta.url)),
);
const ajv = new Ajv({ code: { source: true, esm: true }, unicode: false, allErrors: true });
const validate = ajv.compile(schema);
const code =
    '// Généré depuis contracts/perception.schema.json ; pnpm schema pour actualiser.\n' +
    standalone(ajv, validate) +
    '\n';
const target = new URL('../src/generated/perception-validator.js', import.meta.url);
if (/\brequire\s*\(|new Function\s*\(|\beval\s*\(/.test(code)) {
    throw new Error('Le validateur généré doit rester compatible avec la CSP de Manifest V3.');
}
if (process.argv.includes('--check')) {
    if ((await readFile(target, 'utf8').catch(() => '')) !== code) {
        throw new Error('Schéma frontend périmé : exécuter pnpm schema.');
    }
    console.log('Contrat frontend à jour.');
} else {
    await mkdir(new URL('../src/generated/', import.meta.url), { recursive: true });
    await writeFile(target, code);
    console.log('Validateur de perception généré.');
}
