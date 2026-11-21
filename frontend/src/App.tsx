import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { StadiumBrand } from './design-a1/StadiumKit';
import { requestJson, checkConnection } from './lib/api';
import {
    loadApiUrl,
    saveApiUrl,
    authorizeApi,
    DEFAULT_API_URL,
    normalizeApiUrl,
} from './lib/platform';
import { setSessionApiKey, clearSessionApiKey } from './lib/api-key';
import { scanClub, prepareSbc, type ClubScan } from './lib/club-scan';
import { loadWorkspace, updateProtection } from './lib/sbc-api';
import { credits, type SolverReport } from './lib/sbc-report';
import { fillSbc } from './lib/sbc-fill';

const Diagnostics = lazy(() => import('./Diagnostics'));
type ScanReport = {
    observed: number;
    identified: number;
    pending: number;
    loans: number;
    complete: boolean;
    inventory_updated: boolean;
    protected?: number;
    active_squad?: number;
    protection_policy?: 'preserve' | 'active_squad';
    categories?: Record<string, number>;
    expected_revision: string;
    ocr_readable?: number;
};

export default function App() {
    const [api, setApi] = useState(DEFAULT_API_URL),
        [key, setKey] = useState('');
    const [budget, setBudget] = useState(5000),
        [cap, setCap] = useState(1000);
    const [busy, setBusy] = useState(false),
        [message, setMessage] = useState('Ouvre ton club ou un SBC dans la Web App EA.');
    const [scan, setScan] = useState<ScanReport | null>(null);
    const [authorization, setAuthorization] = useState(false);
    const [proposal, setProposal] = useState<SolverReport | null>(null);
    const [tools, setTools] = useState(false),
        [ready, setReady] = useState(false);
    const current = useRef<AbortController | null>(null);
    useEffect(() => {
        loadApiUrl()
            .then(setApi)
            .catch(() => {})
            .finally(() => setReady(true));
        return () => {
            current.current?.abort();
            clearSessionApiKey();
        };
    }, []);

    async function run(action: 'scan' | 'sbc' | 'basics' | 'authorize-sbc') {
        if (current.current) return;
        const controller = new AbortController();
        current.current = controller;
        setBusy(true);
        setProposal(null);
        setMessage('Connexion…');
        try {
            const base = normalizeApiUrl(api);
            await authorizeApi(base);
            setSessionApiKey(base, key);
            await saveApiUrl(base);
            await checkConnection(base, controller.signal);
            let workspace = await loadWorkspace(base, controller.signal);
            if (workspace.mode !== 'local')
                throw new Error('Les actions EA nécessitent un inventaire local réel.');
            setAuthorization(
                workspace.protection_policy !== 'active_squad' &&
                    workspace.items.length > 0 &&
                    workspace.items.every((c) => c.protected),
            );
            if (action === 'basics' || action === 'authorize-sbc') {
                if (!Number.isSafeInteger(cap) || cap < 1)
                    throw new Error('Choisir un plafond entier positif.');
                const cards = workspace.items.filter(
                    (c) =>
                        c.protected &&
                        !workspace.active_squad_keys?.includes(c.key) &&
                        c.chemistry_kind === 'standard' &&
                        c.value != null &&
                        c.value <= cap,
                );
                // L'autorisation est explicite ; les cartes spéciales et les prix inconnus restent exclus.
                for (const [i, card] of cards.entries()) {
                    setMessage(`Autorisation des cartes de base : ${i + 1}/${cards.length}…`);
                    workspace = await updateProtection(
                        base,
                        workspace,
                        card.key,
                        false,
                        controller.signal,
                    );
                }
                setMessage(
                    `${cards.length} cartes de base sous ${credits(cap)} autorisées pour les prochains calculs.`,
                );
                if (cards.length) setAuthorization(false);
                if (action === 'basics') return;
            }
            if (action === 'scan') {
                const observation: ClubScan = await scanClub(
                    base,
                    controller.signal,
                    setMessage,
                    100,
                );
                const body = {
                    ...observation,
                    expected_revision: workspace.revision,
                    confirmed: false,
                    protection_policy: 'active_squad',
                };
                let report = (await requestJson(
                    base,
                    '/api/v1/sbc/club-scan',
                    {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(body),
                    },
                    controller.signal,
                    15000,
                )) as ScanReport;
                if (report.complete && report.identified) {
                    // Seule l'identification locale est automatique, jamais un échange EA.
                    report = (await requestJson(
                        base,
                        '/api/v1/sbc/club-scan',
                        {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                ...body,
                                expected_revision: report.expected_revision,
                                confirmed: true,
                            }),
                        },
                        controller.signal,
                        15000,
                    )) as ScanReport;
                }
                setScan(report);
                if (report.inventory_updated)
                    setAuthorization(
                        report.protection_policy !== 'active_squad' &&
                            (report.protected ?? report.identified) > 0,
                    );
                setMessage(
                    report.inventory_updated
                        ? `${report.observed} cartes enregistrées · ${report.active_squad ?? 0} joueurs de ton équipe protégés.`
                        : `${report.observed} observations sauvegardées ; le club confirmé est conservé.`,
                );
            } else {
                const result = await prepareSbc(
                    base,
                    workspace,
                    budget,
                    cap,
                    controller.signal,
                    setMessage,
                );
                setProposal(result.report);
                if (['optimal', 'feasible'].includes(result.report.solution.status)) {
                    if (workspace.items.length && workspace.items.every((c) => c.protected)) {
                        setMessage(
                            workspace.protection_policy === 'active_squad'
                                ? 'Les cartes identifiées appartiennent à ton équipe active et restent protégées. Les achats proposés sont manuels.'
                                : `Tes ${workspace.items.length} cartes sont bien enregistrées mais protégées. Autorise tes cartes de base ci-dessous pour utiliser le club. La proposition affichée utilise uniquement le marché.`,
                        );
                        return;
                    }
                    const count = await fillSbc(base, result, controller.signal, setMessage);
                    setMessage(
                        `${count} joueurs placés. Vérifie les conditions dans EA ; la validation reste manuelle.`,
                    );
                    return;
                }
                setMessage(
                    result.report.solution.status === 'infeasible'
                        ? workspace.items.length && workspace.items.every((c) => c.protected)
                            ? `Tes ${workspace.items.length} cartes sont protégées : le calcul utilise seulement des achats. Aucune équipe trouvée dans le catalogue actuel avec ${credits(budget)} de budget et ${credits(cap)} par carte. Autorise tes cartes de base ci-dessous, ou ajuste les limites.`
                            : `Aucune équipe trouvée dans le catalogue actuel avec ${credits(budget)} de budget et ${credits(cap)} par carte. Vérifie les protections et les prix disponibles.`
                        : 'Le calcul n’a pas trouvé de composition dans le temps imparti. Aucun joueur n’a été déplacé.',
                );
            }
        } catch (error) {
            setMessage(
                controller.signal.aborted
                    ? 'Opération arrêtée. Vérifie les cartes déjà placées dans EA.'
                    : error instanceof Error
                      ? error.message
                      : 'Opération impossible.',
            );
        } finally {
            current.current = null;
            setBusy(false);
        }
    }
    if (tools)
        return (
            <Suspense fallback={<p>Chargement…</p>}>
                <button className="text-button" onClick={() => setTools(false)}>
                    ← Retour
                </button>
                <Diagnostics />
            </Suspense>
        );
    return (
        <main className="app-shell stadium-kit stadium-app quick-app">
            <header className="app-header stadium-header">
                <StadiumBrand />
            </header>
            <div className="app-page">
                <div className="quick-actions">
                    <button
                        className="primary-button"
                        disabled={busy || !ready}
                        onClick={() => run('scan')}
                    >
                        Scanner mon club
                    </button>
                    <button
                        className="primary-button"
                        disabled={busy || !ready}
                        onClick={() => run('sbc')}
                    >
                        Compléter ce SBC
                    </button>
                </div>
                <p className="field-hint">La validation finale du SBC reste manuelle.</p>
                <p role="status" className="quick-status">
                    {message}
                </p>
                {authorization && !busy && (
                    <button
                        className="primary-button authorize-button"
                        onClick={() => run(proposal ? 'authorize-sbc' : 'basics')}
                    >
                        Autoriser mes cartes de base sous {credits(cap)}
                        {proposal ? ' et remplir ce SBC' : ''}
                    </button>
                )}
                {busy && (
                    <button className="text-button" onClick={() => current.current?.abort()}>
                        Arrêter
                    </button>
                )}
                {scan?.categories && (
                    <p>
                        {Object.entries(scan.categories)
                            .map(([type, count]) => `${count} ${type}`)
                            .join(' · ')}
                    </p>
                )}
                {proposal && (
                    <section className="panel">
                        <h3>
                            {['optimal', 'feasible'].includes(proposal.solution.status)
                                ? 'Composition proposée'
                                : 'Aucune composition disponible'}
                        </h3>
                        {['optimal', 'feasible'].includes(proposal.solution.status) && (
                            <p>
                                {proposal.selection_scope === 'club' ? 'Club uniquement · ' : ''}
                                {proposal.selection_priority === 'rating_then_value'
                                    ? 'Notes les plus basses · '
                                    : ''}
                                Achats : {credits(proposal.solution.purchase_cost)} · Valeur des
                                cartes utilisées : {credits(proposal.solution.sacrifice_value)}
                            </p>
                        )}
                        <ul>
                            {(proposal.solution.assignments ?? []).map((a) => {
                                const c = proposal.selected_candidates.find(
                                    (c) => c.key === a.candidate_key,
                                );
                                return (
                                    <li key={a.slot}>
                                        {proposal.challenge.positions?.[a.slot] ?? 'Carte'} :{' '}
                                        {c?.name} {c?.rating} · {c?.owned ? 'club' : 'à acheter'}
                                    </li>
                                );
                            })}
                        </ul>
                    </section>
                )}
                <details className="quick-options">
                    <summary>Options</summary>
                    {scan && (
                        <p>
                            {scan.loans} prêts exclus · {Math.max(0, scan.pending - scan.loans)}{' '}
                            versions absentes ou ambiguës dans le catalogue, exclues du calcul.{' '}
                            {scan.identified} cartes identifiées.{' '}
                            {scan.ocr_readable === 0
                                ? 'Aucune carte lue par OCR sur ce passage ; données HTML uniquement.'
                                : ''}
                        </p>
                    )}
                    <label>
                        Budget d’achat{' '}
                        <input
                            type="number"
                            min="0"
                            value={budget}
                            disabled={busy}
                            onChange={(e) => setBudget(Number(e.target.value))}
                        />
                    </label>
                    <label>
                        Valeur maximale par carte{' '}
                        <input
                            type="number"
                            min="1"
                            value={cap}
                            disabled={busy}
                            onChange={(e) => setCap(Number(e.target.value))}
                        />
                    </label>
                    <button
                        className="text-button"
                        disabled={busy || !ready}
                        onClick={() => run('basics')}
                    >
                        Autoriser les cartes de base sous ce plafond
                    </button>
                    <p className="field-hint">
                        Une carte protégée est exclue du calcul. L’autorisation conserve le plafond
                        de valeur. Cartes de base, rares comprises, avec un prix récent inférieur ou
                        égal au plafond.
                    </p>
                    <label>
                        Serveur{' '}
                        <input
                            type="url"
                            value={api}
                            disabled={busy}
                            onChange={(e) => {
                                setApi(e.target.value);
                                setKey('');
                                clearSessionApiKey();
                            }}
                        />
                    </label>
                    <label>
                        Clé API, si demandée{' '}
                        <input
                            type="password"
                            value={key}
                            autoComplete="off"
                            disabled={busy}
                            onChange={(e) => setKey(e.target.value)}
                        />
                    </label>
                    <button className="text-button" disabled={busy} onClick={() => setTools(true)}>
                        Diagnostic et protections des cartes
                    </button>
                </details>
            </div>
        </main>
    );
}
