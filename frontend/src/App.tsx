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
import { loadWorkspace } from './lib/sbc-api';
import { credits, type SolverReport } from './lib/sbc-report';

const Diagnostics = lazy(() => import('./Diagnostics'));
type ScanReport = {
    observed: number;
    identified: number;
    pending: number;
    loans: number;
    complete: boolean;
    inventory_updated: boolean;
};

export default function App() {
    const [api, setApi] = useState(DEFAULT_API_URL),
        [key, setKey] = useState('');
    const [budget, setBudget] = useState(5000),
        [cap, setCap] = useState(1000);
    const [busy, setBusy] = useState(false),
        [message, setMessage] = useState('Ouvre ton club ou un SBC dans la Web App EA.');
    const [scan, setScan] = useState<ScanReport | null>(null);
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

    async function run(action: 'scan' | 'sbc') {
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
            const workspace = await loadWorkspace(base, controller.signal);
            if (workspace.mode !== 'local')
                throw new Error('Les actions EA nécessitent un inventaire local réel.');
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
                            body: JSON.stringify({ ...body, confirmed: true }),
                        },
                        controller.signal,
                        15000,
                    )) as ScanReport;
                }
                setScan(report);
                setMessage(
                    report.inventory_updated
                        ? `${report.observed} cartes enregistrées ; ${report.identified} identifiées et protégées. ${report.pending} restent à vérifier.`
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
                setProposal(result);
                setMessage(
                    ['optimal', 'feasible'].includes(result.solution.status)
                        ? 'Proposition prête. Le placement automatique reste à raccorder ; aucun joueur n’a été échangé.'
                        : result.solution.status === 'infeasible'
                          ? 'Aucune composition ne respecte ces conditions avec les cartes et prix disponibles. Aucun joueur n’a été déplacé.'
                          : 'Le calcul n’a pas trouvé de composition dans le temps imparti. Aucun joueur n’a été déplacé.',
                );
            }
        } catch (error) {
            setMessage(
                controller.signal.aborted
                    ? 'Opération arrêtée.'
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
                {busy && (
                    <button className="text-button" onClick={() => current.current?.abort()}>
                        Arrêter
                    </button>
                )}
                {scan && (
                    <p>
                        {scan.complete ? 'Club parcouru.' : 'Relevé partiel.'} {scan.loans} cartes
                        en prêt exclues.
                    </p>
                )}
                {proposal && (
                    <section className="panel">
                        <h3>
                            {['optimal', 'feasible'].includes(proposal.solution.status)
                                ? 'Composition proposée'
                                : 'Aucune composition disponible'}
                        </h3>
                        <p>
                            Achats : {credits(proposal.solution.purchase_cost)} · Valeur des cartes
                            utilisées : {credits(proposal.solution.sacrifice_value)}
                        </p>
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
