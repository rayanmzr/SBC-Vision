import { useRef, useState, useEffect, type ChangeEvent } from 'react';
import fixture from '../../data/fixtures/sbc-report.synthetic.json';
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

type Scenario = 'optimal' | 'feasible' | 'infeasible' | 'unknown' | 'uncertain';
type Document = { data: ImportedReport; source: 'file' | 'synthetic'; name: string };

export default function SbcWorkspace() {
    const [document, setDocument] = useState<Document | null>(null);
    const [scenario, setScenario] = useState<Scenario>('optimal');
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);
    const [visible, setVisible] = useState(50);
    const [protectionDraft, setProtectionDraft] = useState<Record<string, boolean>>({});
    const request = useRef(0);
    const fileInput = useRef<HTMLInputElement>(null);
    useEffect(
        () => () => {
            request.current++;
        },
        [],
    );

    function example(next: Scenario) {
        request.current++;
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
        const data = structuredClone(fixture);
        data.solution.status = next;
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
            if (request.current === token) setDocument({ data, source: 'file', name: file.name });
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

    return (
        <section className="sbc-workspace" aria-label="Rapport de composition SBC">
            <div className="panel report-toolbar">
                <div>
                    <h3>Ouvrir un rapport du moteur SBC</h3>
                    <p className="field-hint">
                        Lecture locale d’un JSON de Rayan · 2 Mio maximum · aucun envoi au serveur
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
            <div className="report-examples">
                <span>Explorer un scénario fictif</span>
                <select
                    aria-label="Scénario du solveur"
                    value={scenario}
                    disabled={loading}
                    onChange={(event) => example(event.target.value as Scenario)}
                >
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
            {error && (
                <div className="notice" role="alert">
                    <strong>Rapport refusé</strong>
                    <p>{error}</p>
                </div>
            )}
            {!document && !error && (
                <div className="panel report-empty">
                    <h3>Du JSON à la composition proposée</h3>
                    <p>
                        Ouvre une proposition exportée par le moteur ou explore l’exemple fictif
                        pour voir les cartes, les conditions et les achats suggérés.
                    </p>
                    <p className="field-hint">
                        Le raccordement automatique à l’API viendra ensuite.
                    </p>
                </div>
            )}
            {document && (
                <>
                    <div
                        className={
                            document.source === 'synthetic' ? 'synthetic-notice' : 'import-notice'
                        }
                    >
                        <strong>
                            {document.source === 'synthetic'
                                ? 'Exemple synthétique · Aucun calcul exécuté'
                                : importedSynthetic
                                  ? 'Rapport importé · Données fictives'
                                  : 'Rapport importé · Non revérifié en direct'}
                        </strong>
                        <p>
                            {document.source === 'synthetic'
                                ? 'Données préparées à la main pour tester l’interface et ses états.'
                                : document.name}
                        </p>
                    </div>
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
                                        (Paris). Les prix et disponibilités restent à revérifier.
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
                                    Ce sous-ensemble peut inclure des alternatives. Il ne représente
                                    pas l’inventaire complet du club.
                                </p>
                                {document.source === 'synthetic' ? (
                                    <p className="draft-hint">
                                        Les cases de protection modifient seulement cet exemple. Le
                                        club réel reste inchangé.
                                    </p>
                                ) : (
                                    <p className="field-hint">
                                        Protections en lecture seule : leur modification réelle
                                        attend le raccordement à l’inventaire.
                                    </p>
                                )}
                                <div className="candidate-grid">
                                    {cards.slice(0, visible).map((card) => (
                                        <article key={card.key} className="candidate-card">
                                            <div className="candidate-heading">
                                                <span className="rating-token">{card.rating}</span>
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
                                                        card.value == null ? 'unknown-price' : ''
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
                            {showComposition && (
                                <section
                                    className="panel report-shopping"
                                    aria-labelledby="shopping-title"
                                >
                                    <h3 id="shopping-title">Achats suggérés</h3>
                                    <p className="field-hint">
                                        Prix du rapport uniquement : ils ne garantissent pas une
                                        offre disponible.
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
                                                            Version {card.card_id} ·{' '}
                                                            {card.positions.join(' / ')}
                                                        </small>
                                                    </div>
                                                    <div className="shopping-price">
                                                        <strong>
                                                            {credits(card.value)} / carte
                                                        </strong>
                                                        <small>
                                                            Total :{' '}
                                                            {credits(card.value! * quantity)}
                                                        </small>
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
