import {
    useRef,
    useState,
    useEffect,
    useCallback,
    useId,
    type ChangeEvent,
    type ReactNode,
} from 'react';
import SbcApiPanel from './SbcApiPanel';
import SbcSquadPreview from './SbcSquadPreview';
import { squadLayout } from './lib/squad-layout';
import { DEFAULT_API_URL } from './lib/platform';
import type { ApiProposal } from './lib/sbc-api';
import fixture from '../../data/fixtures/sbc-report.synthetic.json';
import stadiumFixture from '../../data/fixtures/sbc-report-a1.synthetic.json';
import {
    conditionLabel,
    credits,
    parseSolverReport,
    purchases,
    readSolverFile,
    isSyntheticReport,
    type ImportedReport,
    type SolverReport,
} from './lib/sbc-report';

type Scenario = 'eleven' | 'optimal' | 'feasible' | 'infeasible' | 'unknown' | 'uncertain';
type Document = {
    data: ImportedReport;
    source: 'file' | 'synthetic' | 'api';
    name: string;
    mode?: 'demo' | 'local';
};
const noConnection = async () => false;

export default function SbcWorkspace({
    apiUrl = DEFAULT_API_URL,
    connected = false,
    onConnect = noConnection,
}: {
    apiUrl?: string;
    connected?: boolean;
    onConnect?: () => Promise<boolean>;
}) {
    const [source, setSource] = useState<'api' | 'file' | 'example'>('api');
    const [document, setDocument] = useState<Document | null>(null);
    const [scenario, setScenario] = useState<Scenario>('optimal');
    const [inputsOpen, setInputsOpen] = useState(false);
    const [shoppingOpen, setShoppingOpen] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);
    const [visible, setVisible] = useState(50);
    const [protectionDraft, setProtectionDraft] = useState<Record<string, boolean>>({});
    const request = useRef(0);
    const fileInput = useRef<HTMLInputElement>(null);
    const apiReset = useCallback(
        () => setDocument((previous) => (previous?.source === 'api' ? null : previous)),
        [],
    );
    const apiStart = useCallback(() => {
        const token = ++request.current;
        setLoading(false);
        setDocument(null);
        setError(null);
        setProtectionDraft({});
        setInputsOpen(false);
        setShoppingOpen(false);
        return token;
    }, []);
    const apiReport = useCallback((proposal: ApiProposal, token: number) => {
        if (request.current !== token) return;
        setDocument({
            source: 'api',
            mode: proposal.mode,
            name: 'Proposition calculée par l’API',
            data: { kind: 'solver', report: proposal.report },
        });
        setProtectionDraft({});
        setVisible(50);
        setInputsOpen(false);
        setShoppingOpen(false);
    }, []);
    function changeSource(next: typeof source) {
        request.current++;
        setInputsOpen(false);
        setShoppingOpen(false);
        setSource(next);
        setLoading(false);
        setDocument(null);
        setError(null);
        setProtectionDraft({});
    }
    useEffect(
        () => () => {
            request.current++;
        },
        [],
    );

    function example(next: Scenario) {
        request.current++;
        setInputsOpen(false);
        setShoppingOpen(false);
        setLoading(false);
        setError(null);
        setProtectionDraft({});
        setVisible(50);
        setScenario(next);
        if (next === 'uncertain') {
            setDocument({
                source: 'synthetic',
                name: 'Lecture fictive à confirmer',
                data: {
                    kind: 'uncertain',
                    issues: [
                        'Le poste d’une carte est illisible.',
                        'Une condition du SBC doit être relue.',
                    ],
                },
            });
            return;
        }
        const data = structuredClone(next === 'eleven' ? stadiumFixture : fixture);
        data.solution.status = next === 'eleven' ? 'feasible' : next;
        if (next === 'infeasible' || next === 'unknown') {
            Object.assign(data.solution, {
                assignments: [],
                purchase_cost: null,
                sacrifice_value: null,
                total_cost: null,
                errors: [
                    next === 'infeasible'
                        ? 'Aucune combinaison admissible dans le pool de cet exemple.'
                        : 'La recherche s’est arrêtée sans pouvoir conclure.',
                ],
            });
            Object.assign(data, { verification: null });
        }
        setDocument({
            source: 'synthetic',
            name: 'Rapport fictif de visualisation',
            data: parseSolverReport(data),
        });
    }

    async function importFile(event: ChangeEvent<HTMLInputElement>) {
        const file = event.target.files?.[0];
        event.target.value = '';
        if (!file) return;
        const token = ++request.current;
        setLoading(true);
        setError(null);
        setDocument(null);
        setProtectionDraft({});
        setVisible(50);
        try {
            const data = await readSolverFile(file);
            if (request.current === token) {
                setDocument({ data, source: 'file', name: file.name });
                setInputsOpen(false);
                setShoppingOpen(false);
            }
        } catch (failure) {
            if (request.current === token)
                setError(failure instanceof Error ? failure.message : 'Rapport illisible.');
        } finally {
            if (request.current === token) setLoading(false);
        }
    }

    const parsed = document?.data;
    const report = parsed?.kind === 'solver' ? parsed.report : null;
    const successful = report && ['optimal', 'feasible'].includes(report.solution.status);
    const dirty = Object.keys(protectionDraft).length > 0;
    const showComposition = successful && !dirty;
    const cards = report?.selected_candidates ?? [];
    const importedSynthetic = document?.source === 'file' && report && isSyntheticReport(report);
    const statusLabels = {
        optimal: 'Proposition optimale selon le rapport',
        feasible: 'Proposition faisable selon le rapport',
        infeasible: 'Aucune solution sur le pool connu',
        unknown: 'Recherche sans conclusion',
    };
    const costs = report?.solution;
    const hasHero = !!(showComposition && report && squadLayout(report));
    const sourceLabel =
        document?.source === 'synthetic' || importedSynthetic || document?.mode === 'demo'
            ? 'Exemple fictif'
            : document?.source === 'api'
              ? 'Réponse API'
              : 'Rapport importé';

    return (
        <section className="sbc-workspace" aria-label="Rapport de composition SBC">
            <div className="report-input-area">
                {hasHero && (
                    <button
                        className="report-input-toggle"
                        aria-expanded={inputsOpen}
                        aria-controls="report-inputs"
                        onClick={() => setInputsOpen((value) => !value)}
                    >
                        {inputsOpen ? 'Fermer les sources' : 'Sources et inventaire'}
                        <span aria-hidden="true">{inputsOpen ? '−' : '+'}</span>
                    </button>
                )}
                <div id="report-inputs" hidden={hasHero && !inputsOpen}>
                    <nav className="workspace-nav source-nav" aria-label="Source de la composition">
                        <button aria-pressed={source === 'api'} onClick={() => changeSource('api')}>
                            Depuis l’API
                        </button>
                        <button
                            aria-pressed={source === 'file'}
                            onClick={() => changeSource('file')}
                        >
                            Rapport local
                        </button>
                        <button
                            aria-pressed={source === 'example'}
                            onClick={() => changeSource('example')}
                        >
                            Exemple fictif
                        </button>
                    </nav>
                    <div hidden={source !== 'api'}>
                        <SbcApiPanel
                            apiUrl={apiUrl}
                            connected={connected}
                            active={source === 'api'}
                            onConnect={onConnect}
                            onStart={apiStart}
                            onReport={apiReport}
                            onReset={apiReset}
                        />
                    </div>
                    <div hidden={source !== 'file'}>
                        <div className="panel report-toolbar">
                            <div>
                                <h3>Ouvrir un rapport du moteur SBC</h3>
                                <p className="field-hint">
                                    Lecture locale d’un JSON de Rayan · 2 Mio maximum · aucun envoi
                                    au serveur
                                </p>
                            </div>
                            <input
                                ref={fileInput}
                                className="visually-hidden"
                                type="file"
                                accept=".json,application/json"
                                aria-label="Importer un rapport SBC JSON"
                                onChange={importFile}
                            />
                            <button
                                className="secondary-button"
                                onClick={() => fileInput.current?.click()}
                                disabled={loading}
                            >
                                {loading ? 'Lecture en cours…' : 'Ouvrir un rapport JSON'}
                            </button>
                        </div>
                    </div>
                    <div hidden={source !== 'example'}>
                        <div className="report-examples">
                            <span>Explorer un scénario fictif</span>
                            <select
                                aria-label="Scénario du solveur"
                                value={scenario}
                                disabled={loading}
                                onChange={(event) => example(event.target.value as Scenario)}
                            >
                                <option value="eleven">Maquette A1 · 11 cartes</option>
                                <option value="optimal">Solution optimale</option>
                                <option value="feasible">Solution faisable</option>
                                <option value="infeasible">Aucune solution</option>
                                <option value="unknown">Recherche sans conclusion</option>
                                <option value="uncertain">Lecture incertaine</option>
                            </select>
                            <button
                                className="text-button"
                                onClick={() => example(scenario)}
                                disabled={loading}
                            >
                                Charger l’exemple du solveur →
                            </button>
                        </div>
                    </div>
                </div>
            </div>
            {error && (
                <div className="notice" role="alert">
                    <strong>Rapport refusé</strong>
                    <p>{error}</p>
                </div>
            )}
            {!document && !error && source !== 'api' && (
                <div className="panel report-empty">
                    <h3>Du JSON à la composition proposée</h3>
                    <p>
                        Ouvre une proposition exportée par le moteur ou explore l’exemple fictif
                        pour voir les cartes, les conditions et les achats suggérés.
                    </p>
                    <p className="field-hint">
                        L’onglet Depuis l’API permet de lancer un calcul sur le serveur.
                    </p>
                </div>
            )}
            {document && (
                <>
                    {hasHero && report && (
                        <SbcSquadPreview
                            key={document.name + JSON.stringify(report.solution.assignments)}
                            report={report}
                            sourceLabel={sourceLabel}
                            shoppingOpen={shoppingOpen}
                            onShopping={() => setShoppingOpen((value) => !value)}
                        />
                    )}
                    {hasHero && report && (
                        <div id="report-shopping-content" hidden={!shoppingOpen}>
                            <ShoppingReport report={report} />
                        </div>
                    )}
                    <ReportFold
                        title={
                            document.source === 'synthetic'
                                ? 'Exemple synthétique · Aucun calcul exécuté'
                                : document.source === 'api'
                                  ? document.mode === 'demo'
                                      ? 'API de démonstration · Calcul CP-SAT réel'
                                      : 'Proposition reçue de l’API · À vérifier dans le jeu'
                                  : importedSynthetic
                                    ? 'Rapport importé · Données fictives'
                                    : 'Rapport importé · Non revérifié en direct'
                        }
                        folded={hasHero}
                        className="report-provenance"
                    >
                        <div
                            className={
                                document.source === 'synthetic'
                                    ? 'synthetic-notice'
                                    : 'import-notice'
                            }
                        >
                            {!hasHero && (
                                <strong>
                                    {document.source === 'synthetic'
                                        ? 'Exemple synthétique · Aucun calcul exécuté'
                                        : document.source === 'api'
                                          ? document.mode === 'demo'
                                              ? 'API de démonstration · Calcul CP-SAT réel'
                                              : 'Proposition reçue de l’API · À vérifier dans le jeu'
                                          : importedSynthetic
                                            ? 'Rapport importé · Données fictives'
                                            : 'Rapport importé · Non revérifié en direct'}
                                </strong>
                            )}
                            <p>
                                {document.source === 'synthetic'
                                    ? 'Données préparées à la main pour tester l’interface et ses états.'
                                    : document.name}
                            </p>
                        </div>
                    </ReportFold>
                    {parsed?.kind === 'uncertain' && (
                        <div className="panel report-state" role="status">
                            <h3>Lecture à confirmer</h3>
                            <p>
                                Les informations incertaines doivent être corrigées avant de
                                proposer une équipe.
                            </p>
                            <ul>
                                {parsed.issues.map((issue, index) => (
                                    <li key={index}>{issue}</li>
                                ))}
                            </ul>
                        </div>
                    )}
                    {report && (
                        <>
                            <ReportFold title="État et vérification du rapport" folded={hasHero}>
                                <div
                                    className={`panel report-state ${showComposition ? 'report-success' : ''}`}
                                    role="status"
                                >
                                    <h3>
                                        {dirty
                                            ? 'Recalcul nécessaire'
                                            : statusLabels[report.solution.status]}
                                    </h3>
                                    <p>
                                        {dirty
                                            ? 'Une protection a changé dans cet exemple. L’ancienne composition et ses coûts sont retirés jusqu’à un nouveau calcul.'
                                            : successful
                                              ? 'Ce résultat concerne les cartes et les règles connues du moteur. Il ne constitue pas une validation par EA.'
                                              : report.solution.status === 'infeasible'
                                                ? 'Cela ne prouve pas qu’aucune autre équipe existe dans le jeu.'
                                                : 'Le moteur n’a pas prouvé l’absence de solution.'}
                                    </p>
                                    {report.solution.errors?.length ? (
                                        <ul>
                                            {report.solution.errors.map((message, index) => (
                                                <li key={index}>{message}</li>
                                            ))}
                                        </ul>
                                    ) : null}
                                </div>
                            </ReportFold>
                            {!hasHero && (
                                <div className="cost-grid" aria-label="Coûts du rapport">
                                    <Cost
                                        label="Achats suggérés"
                                        value={showComposition ? costs?.purchase_cost : null}
                                    />
                                    <Cost
                                        label="Valeur des cartes utilisées"
                                        value={showComposition ? costs?.sacrifice_value : null}
                                    />
                                    <Cost
                                        label="Coût économique total"
                                        value={showComposition ? costs?.total_cost : null}
                                    />
                                </div>
                            )}
                            <ReportFold title="Conditions et composition" folded={hasHero}>
                                <div className="report-grid">
                                    <section className="panel" aria-labelledby="conditions-title">
                                        <div className="report-section-heading">
                                            <h3 id="conditions-title">Conditions du SBC</h3>
                                            <span className="kind-label">
                                                {report.challenge.market.toUpperCase()}
                                            </span>
                                        </div>
                                        <p className="budget-line">
                                            Budget d’achat :{' '}
                                            <strong>{credits(report.challenge.budget)}</strong>
                                        </p>
                                        {report.challenge.max_card_value != null && (
                                            <p className="field-hint">
                                                Plafond par carte :{' '}
                                                {credits(report.challenge.max_card_value)}
                                            </p>
                                        )}
                                        <ul className="conditions-list">
                                            {(report.challenge.conditions ?? []).map(
                                                (condition, index) => (
                                                    <li key={index}>{conditionLabel(condition)}</li>
                                                ),
                                            )}
                                        </ul>
                                        {!(report.challenge.conditions ?? []).length && (
                                            <p className="field-hint">
                                                Aucune condition supplémentaire renseignée.
                                            </p>
                                        )}
                                        <p className="price-date">
                                            Référence des prix :{' '}
                                            {new Intl.DateTimeFormat('fr-FR', {
                                                dateStyle: 'short',
                                                timeStyle: 'short',
                                                timeZone: 'Europe/Paris',
                                            }).format(new Date(report.price_reference_at))}{' '}
                                            (Paris). Les prix et disponibilités restent à
                                            revérifier.
                                        </p>
                                    </section>
                                    <section className="panel" aria-labelledby="composition-title">
                                        <h3 id="composition-title">Composition annoncée</h3>
                                        {showComposition ? (
                                            <Composition report={report} />
                                        ) : (
                                            <p className="report-placeholder">
                                                {dirty
                                                    ? 'Proposition à recalculer.'
                                                    : 'Aucune composition à afficher.'}
                                            </p>
                                        )}
                                        {showComposition && (
                                            <p className="field-hint">
                                                {report.verification?.valid
                                                    ? 'Vérification locale déclarée dans le rapport.'
                                                    : 'Aucune vérification locale positive fournie.'}
                                            </p>
                                        )}
                                    </section>
                                </div>
                            </ReportFold>
                            <ReportFold title="Cartes et protections" folded={hasHero}>
                                <section
                                    className="panel report-cards"
                                    aria-labelledby="report-cards-title"
                                >
                                    <div className="report-section-heading">
                                        <h3 id="report-cards-title">
                                            Cartes présentes dans le rapport
                                        </h3>
                                        <span className="kind-label">{cards.length} candidats</span>
                                    </div>
                                    <p className="field-hint">
                                        Ce sous-ensemble peut inclure des alternatives. Il ne
                                        représente pas l’inventaire complet du club.
                                    </p>
                                    {document.source === 'synthetic' ? (
                                        <p className="draft-hint">
                                            Les cases de protection modifient seulement cet exemple.
                                            Le club réel reste inchangé.
                                        </p>
                                    ) : (
                                        <p className="field-hint">
                                            Protections du rapport en lecture seule. Utiliser
                                            l’inventaire de l’API pour les modifier sur le serveur.
                                        </p>
                                    )}
                                    <div className="candidate-grid">
                                        {cards.slice(0, visible).map((card) => (
                                            <article key={card.key} className="candidate-card">
                                                <div className="candidate-heading">
                                                    <span className="rating-token">
                                                        {card.rating}
                                                    </span>
                                                    <div>
                                                        <h4>{card.name}</h4>
                                                        <p>
                                                            {card.positions.join(' / ')} · version{' '}
                                                            {card.card_id}
                                                        </p>
                                                    </div>
                                                </div>
                                                <div className="candidate-meta">
                                                    <span>
                                                        {card.owned
                                                            ? 'Exemplaire du club'
                                                            : 'Candidat du marché'}
                                                    </span>
                                                    <strong
                                                        className={
                                                            card.value == null
                                                                ? 'unknown-price'
                                                                : ''
                                                        }
                                                    >
                                                        {credits(card.value)}
                                                    </strong>
                                                </div>
                                                <label className="protection-control">
                                                    <input
                                                        type="checkbox"
                                                        aria-label={`Protéger ${card.name} ${card.key}`}
                                                        disabled={
                                                            document.source !== 'synthetic' ||
                                                            !card.owned
                                                        }
                                                        checked={
                                                            protectionDraft[card.key] ??
                                                            card.protected ??
                                                            false
                                                        }
                                                        onChange={(event) =>
                                                            setProtectionDraft((previous) => ({
                                                                ...previous,
                                                                [card.key]: event.target.checked,
                                                            }))
                                                        }
                                                    />
                                                    {(protectionDraft[card.key] ?? card.protected)
                                                        ? 'Carte protégée'
                                                        : card.owned
                                                          ? 'Carte utilisable'
                                                          : 'Protection sans objet'}
                                                </label>
                                                <small className="candidate-key">{card.key}</small>
                                            </article>
                                        ))}
                                    </div>
                                    {visible < cards.length && (
                                        <button
                                            className="text-button"
                                            onClick={() => setVisible((value) => value + 50)}
                                        >
                                            Afficher 50 cartes supplémentaires
                                        </button>
                                    )}
                                </section>
                            </ReportFold>
                            {showComposition && !hasHero && (
                                <div>
                                    <ShoppingReport report={report} />
                                </div>
                            )}
                            <details className="json-details report-json">
                                <summary>
                                    {dirty
                                        ? 'Voir le JSON original (proposition obsolète)'
                                        : 'Voir le JSON du rapport'}
                                </summary>
                                <pre>{JSON.stringify(report, null, 2)}</pre>
                            </details>
                        </>
                    )}
                </>
            )}
        </section>
    );
}

function Cost({ label, value }: { label: string; value: number | null | undefined }) {
    return (
        <div className="panel cost-card">
            <span>{label}</span>
            <strong>{value == null ? '—' : credits(value)}</strong>
        </div>
    );
}

function Composition({ report }: { report: SolverReport }) {
    const byKey = new Map(report.selected_candidates.map((card) => [card.key, card]));
    if (!(report.solution.assignments ?? []).length)
        return <p className="report-placeholder">Le rapport ne propose aucun nouvel exemplaire.</p>;
    return (
        <ol className="composition-list">
            {(report.solution.assignments ?? [])
                .slice()
                .sort((a, b) => a.slot - b.slot)
                .map((assignment) => {
                    const card = byKey.get(assignment.candidate_key)!;
                    return (
                        <li key={assignment.slot}>
                            <span className="slot-token">
                                {report.challenge.positions?.[assignment.slot] ??
                                    `#${assignment.slot + 1}`}
                            </span>
                            <div>
                                <strong>{card.name}</strong>
                                <small>
                                    Version {card.card_id} · {card.owned ? 'Club' : 'Achat suggéré'}
                                </small>
                            </div>
                            <span>{card.rating}</span>
                        </li>
                    );
                })}
        </ol>
    );
}

function ReportFold({
    title,
    folded,
    className = '',
    children,
}: {
    title: string;
    folded: boolean;
    className?: string;
    children: ReactNode;
}) {
    const [expanded, setExpanded] = useState(false);
    const contentId = useId();
    return (
        <section className={`report-fold ${className}`}>
            {folded && (
                <button
                    className="report-fold-toggle"
                    type="button"
                    aria-expanded={expanded}
                    aria-controls={contentId}
                    onClick={() => setExpanded((value) => !value)}
                >
                    {title}
                    <span aria-hidden="true">{expanded ? '−' : '+'}</span>
                </button>
            )}
            <div id={contentId} hidden={folded && !expanded}>
                {children}
            </div>
        </section>
    );
}

function ShoppingReport({ report }: { report: SolverReport }) {
    return (
        <section className="panel report-shopping" aria-labelledby="shopping-title">
            <h3 id="shopping-title">Achats suggérés</h3>
            <p className="field-hint">
                Prix du rapport uniquement : ils ne garantissent pas une offre disponible.
            </p>
            {purchases(report).length ? (
                <ul>
                    {purchases(report).map(({ card, quantity }) => (
                        <li key={card.key}>
                            <div>
                                <strong>
                                    {quantity} × {card.name}
                                </strong>
                                <small>
                                    Version {card.card_id} · {card.positions.join(' / ')}
                                </small>
                            </div>
                            <div className="shopping-price">
                                <strong>{credits(card.value)} / carte</strong>
                                <small>Total : {credits(card.value! * quantity)}</small>
                            </div>
                        </li>
                    ))}
                </ul>
            ) : (
                <p className="report-placeholder">
                    Tous les exemplaires proposés proviennent du club.
                </p>
            )}
        </section>
    );
}
