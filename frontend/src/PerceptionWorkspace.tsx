import { useEffect, useRef, useState, type ChangeEvent } from 'react';
import { StadiumIcon } from './design-a1/StadiumKit';
import { isExtension } from './lib/platform';
import { imagePointToViewport, type TabCapture } from './lib/tab-capture';
import type { ElementKind, Perception } from './lib/api';
import { requestJson } from './lib/api';
import { loadWorkspace } from './lib/sbc-api';
import { DEFAULT_API_URL } from './lib/platform';
import type { SolverReport } from './lib/sbc-report';
import { scanClub, type ClubScan } from './lib/club-scan';

export type CaptureSelection = {
    file: File;
    url: string;
    width: number;
    height: number;
    tab?: TabCapture;
};
export type PerceptionResult = { data: Perception; source: 'api' | 'synthetic'; imageUrl: string };
type Props = {
    selection: CaptureSelection | null;
    result: PerceptionResult | null;
    connected: boolean;
    busy: string | null;
    onChoose: (event: ChangeEvent<HTMLInputElement>) => void;
    onCapture: () => void;
    onAnalyze: () => void;
    onExample: () => void;
    onSettings: () => void;
    onClear: () => void;
    apiUrl?: string;
    onChallenge?: (challenge: SolverReport['challenge']) => void;
    onScanRunning?: (running: boolean) => void;
};
const kinds: Record<ElementKind, string> = {
    button: 'Bouton',
    input: 'Champ',
    link: 'Lien',
    menu: 'Menu',
    checkbox: 'Case à cocher',
    card: 'Carte',
    slot: 'Emplacement',
    text: 'Texte',
};
const actions = { click: 'Clic', fill: 'Saisie', select: 'Sélection', scroll: 'Défilement' };

export default function PerceptionWorkspace({
    selection,
    result,
    connected,
    busy,
    onChoose,
    onCapture,
    onAnalyze,
    onExample,
    onSettings,
    onClear,
    apiUrl = DEFAULT_API_URL,
    onChallenge,
    onScanRunning,
}: Props) {
    const fileInput = useRef<HTMLInputElement>(null);
    const [sourcesOpen, setSourcesOpen] = useState(false);
    const [chosen, setChosen] = useState<{ capture: string; id: string } | null>(null);
    const preview = result?.imageUrl ?? selection?.url;
    const synthetic = result?.source === 'synthetic';
    const elements = result?.data.elements ?? [];
    const selected =
        (chosen?.capture === result?.data.capture_id &&
            elements.find((element) => element.id === chosen?.id)) ||
        elements[0];
    const chooseElement = (id: string) => setChosen({ capture: result!.data.capture_id, id });
    const filename = synthetic ? 'Capture de démonstration' : selection?.file.name;
    const dimensions = result?.data.image ?? selection;
    const stage = result ? 'result' : preview ? 'preview' : 'empty';

    return (
        <section
            className="analysis-workspace"
            data-stage={stage}
            data-has-preview={!!preview}
            aria-label="Analyse d’une capture"
        >
            <div className="analysis-stage-rail" aria-label="Étapes de l’analyse">
                <span data-current={stage === 'empty'} data-complete={!!preview}>
                    <b>01</b>Capture
                </span>
                <span data-current={stage === 'preview'} data-complete={!!result}>
                    <b>02</b>Analyse
                </span>
                <span data-current={stage === 'result'}>
                    <b>03</b>Lecture
                </span>
            </div>
            <div className="analysis-connection-bar">
                <span>
                    <span className={`status-dot ${connected ? 'connected' : ''}`} />
                    {connected
                        ? 'Serveur connecté'
                        : 'Connecte le serveur pour lancer une analyse.'}
                </span>
                <button className="text-button" onClick={onSettings} disabled={!!busy}>
                    Réglages API
                    <StadiumIcon name="arrow" />
                </button>
            </div>
            {preview && (
                <div className="analysis-source-toolbar">
                    <button
                        className="report-input-toggle"
                        aria-expanded={sourcesOpen}
                        aria-controls="capture-sources"
                        disabled={!!busy}
                        onClick={() => setSourcesOpen((value) => !value)}
                    >
                        {sourcesOpen ? 'Fermer les sources' : 'Changer de capture'}
                        <span aria-hidden="true">{sourcesOpen ? '−' : '+'}</span>
                    </button>
                    <button
                        className="text-button"
                        disabled={!!busy}
                        onClick={() => {
                            setSourcesOpen(false);
                            setChosen(null);
                            onClear();
                        }}
                    >
                        Retirer
                    </button>
                </div>
            )}
            {isExtension() && (
                <ClubScanPanel
                    key={apiUrl}
                    apiUrl={apiUrl}
                    connected={connected}
                    disabled={!!busy}
                    onRunning={onScanRunning}
                />
            )}
            <div className="analysis-layout">
                <div
                    id="capture-sources"
                    className="analysis-acquisition"
                    hidden={!!preview && !sourcesOpen}
                >
                    <section className="panel capture-source-panel" aria-labelledby="image-title">
                        <div className="section-heading">
                            <span className="step">
                                <StadiumIcon name="scan" />
                            </span>
                            <div>
                                <h3 id="image-title">Choisir une capture</h3>
                                <p className="capture-subtitle">
                                    Le point de départ de votre analyse.
                                </p>
                            </div>
                        </div>
                        <button
                            className="capture-tab-action"
                            onClick={() => {
                                setSourcesOpen(false);
                                onCapture();
                            }}
                            aria-label={
                                busy === 'capture' ? 'Capture en cours…' : 'Capturer l’onglet actif'
                            }
                            disabled={!isExtension() || !!busy}
                        >
                            <StadiumIcon name="scan" />
                            <span>
                                <strong>
                                    {busy === 'capture'
                                        ? 'Capture en cours…'
                                        : 'Capturer l’onglet actif'}
                                </strong>
                                <small>La zone visible de votre navigateur</small>
                            </span>
                            <StadiumIcon name="arrow" />
                        </button>
                        <p className="field-hint capture-hint">
                            {isExtension()
                                ? 'La capture reste locale jusqu’à son envoi.'
                                : 'Disponible dans le popup Chrome de l’extension.'}
                        </p>
                        <div className="capture-separator">
                            <span>ou importer une image</span>
                        </div>
                        <input
                            ref={fileInput}
                            id="capture-file"
                            className="visually-hidden"
                            type="file"
                            accept="image/png,image/jpeg"
                            aria-label="Choisir une image PNG ou JPEG"
                            onChange={(event) => {
                                setSourcesOpen(false);
                                onChoose(event);
                            }}
                            disabled={!!busy}
                        />
                        <button
                            className="file-picker"
                            aria-label={`${selection ? 'Changer l’image' : 'Choisir une image'} PNG ou JPEG · 5 Mio maximum`}
                            onClick={() => fileInput.current?.click()}
                            disabled={!!busy}
                        >
                            <span className="file-icon">
                                <StadiumIcon name="image" />
                            </span>
                            <strong>{selection ? 'Changer l’image' : 'Choisir une image'}</strong>
                            <span>PNG ou JPEG · 5 Mio maximum</span>
                        </button>
                        {!preview && (
                            <div className="capture-submit-placeholder">
                                <button className="primary-button full-width" disabled>
                                    Envoyer à l’API
                                    <StadiumIcon name="arrow" />
                                </button>
                                <p className="field-hint">
                                    Choisis une image, puis vérifie son aperçu.
                                </p>
                            </div>
                        )}
                        <div className="example-choice">
                            <span>Découvrir l’interface sans envoyer d’image</span>
                            <button
                                className="text-button"
                                onClick={() => {
                                    setSourcesOpen(false);
                                    onExample();
                                }}
                                disabled={!!busy}
                            >
                                Voir un exemple synthétique
                                <StadiumIcon name="arrow" />
                            </button>
                        </div>
                    </section>
                </div>
                <section className="analysis-canvas-panel" aria-labelledby="results-title">
                    {preview ? (
                        <>
                            <div className="analysis-preview-heading">
                                <h3 id="results-title">
                                    {result ? 'Examiner le résultat' : 'Votre capture'}
                                </h3>
                                <span className={`source-badge ${synthetic ? 'synthetic' : ''}`}>
                                    {synthetic
                                        ? 'EXEMPLE FICTIF'
                                        : result
                                          ? 'RÉPONSE API'
                                          : 'CAPTURE LOCALE'}
                                </span>
                            </div>
                            <div className="capture-file-strip">
                                <StadiumIcon name="image" />
                                <div>
                                    <strong>{filename}</strong>
                                    <span>
                                        {dimensions?.width} × {dimensions?.height} px
                                        {selection && !synthetic
                                            ? ` · ${(selection.file.size / 1024).toFixed(1)} Kio`
                                            : ''}
                                    </span>
                                </div>
                            </div>
                            {synthetic && (
                                <div className="synthetic-notice">
                                    <strong>Exemple synthétique · Données fictives</strong>
                                    <p>
                                        Cette image et ses rectangles sont préparés pour la
                                        démonstration. Aucune analyse du modèle n’a été exécutée.
                                    </p>
                                </div>
                            )}
                            <div className="image-preview">
                                <img
                                    src={preview}
                                    alt={
                                        synthetic
                                            ? 'Interface synthétique utilisée pour tester les échanges'
                                            : 'Capture choisie pour l’analyse'
                                    }
                                />
                                {result && (
                                    <svg
                                        className="box-overlay"
                                        viewBox={`0 0 ${result.data.image.width} ${result.data.image.height}`}
                                        aria-label="Localisation des éléments détectés"
                                        role="group"
                                    >
                                        {elements.map((element, index) => (
                                            <g
                                                key={element.id}
                                                className={
                                                    selected?.id === element.id
                                                        ? 'detected-box selected'
                                                        : 'detected-box'
                                                }
                                            >
                                                <rect
                                                    x={element.bbox.x}
                                                    y={element.bbox.y}
                                                    width={element.bbox.width}
                                                    height={element.bbox.height}
                                                    vectorEffect="non-scaling-stroke"
                                                    role="button"
                                                    tabIndex={0}
                                                    aria-label={`Afficher le repère ${index + 1} : ${element.text || element.id}`}
                                                    aria-pressed={selected?.id === element.id}
                                                    onClick={() => chooseElement(element.id)}
                                                    onKeyDown={(event) => {
                                                        if (
                                                            event.key === 'Enter' ||
                                                            event.key === ' '
                                                        ) {
                                                            event.preventDefault();
                                                            chooseElement(element.id);
                                                        }
                                                    }}
                                                >
                                                    <title>
                                                        {kinds[element.kind]} :{' '}
                                                        {element.text ?? element.id}
                                                    </title>
                                                </rect>
                                                <text
                                                    x={element.bbox.x + 4}
                                                    y={Math.max(18, element.bbox.y - 7)}
                                                >
                                                    {index + 1}
                                                </text>
                                            </g>
                                        ))}
                                    </svg>
                                )}
                            </div>
                            {!result && (
                                <div className="capture-ready">
                                    <span>
                                        <StadiumIcon name="image" />
                                        Aperçu prêt · Envoi manuel
                                    </span>
                                    <p>Vérifie l’image avant de l’envoyer au serveur.</p>
                                    <div className="stadium-action-row">
                                        <button
                                            className="primary-button full-width"
                                            disabled={!selection || !connected || !!busy}
                                            onClick={onAnalyze}
                                        >
                                            {busy === 'analysis'
                                                ? 'Analyse en cours…'
                                                : 'Envoyer à l’API'}
                                            <StadiumIcon name="arrow" />
                                        </button>
                                    </div>
                                    <p className="field-hint">
                                        L’envoi commence uniquement avec ce bouton.
                                    </p>
                                </div>
                            )}
                            {selection?.tab && !synthetic && (
                                <details className="capture-origin">
                                    <summary>Capture locale de l’onglet</summary>
                                    <div className="capture-context">
                                        <span>
                                            {new URL(selection.tab.context.viewport.href).origin}
                                        </span>
                                        <span>
                                            Zone visible : {selection.tab.context.viewport.width} ×{' '}
                                            {selection.tab.context.viewport.height} px CSS
                                        </span>
                                        <span>
                                            Échelle image/page :{' '}
                                            {(
                                                selection.width /
                                                selection.tab.context.viewport.width
                                            ).toFixed(2)}
                                            ×
                                        </span>
                                        <span>Aucun clic effectué.</span>
                                    </div>
                                </details>
                            )}
                            {result && (
                                <>
                                    <div className="result-summary">
                                        <h4>
                                            {elements.length} élément
                                            {elements.length !== 1 ? 's' : ''}
                                        </h4>
                                        <span>
                                            {synthetic
                                                ? 'Exemple de lecture'
                                                : 'Lecture du serveur'}
                                        </span>
                                    </div>
                                    {!elements.length && (
                                        <p className="empty-detection">
                                            L’analyse a réussi, mais aucun élément n’a été détecté.
                                        </p>
                                    )}
                                    {!!elements.length && (
                                        <p className="analysis-inspect-hint">
                                            Sélectionne un élément pour retrouver son repère sur
                                            l’image.
                                        </p>
                                    )}
                                    <ol className="analysis-element-list">
                                        {elements.map((element, index) => (
                                            <li key={element.id}>
                                                <button
                                                    type="button"
                                                    className="analysis-element-button"
                                                    aria-pressed={selected?.id === element.id}
                                                    aria-label={`Afficher l’élément ${index + 1} : ${element.text || element.id}`}
                                                    onClick={() => chooseElement(element.id)}
                                                >
                                                    <span className="element-number">
                                                        {index + 1}
                                                    </span>
                                                    <span className="analysis-element-copy">
                                                        <span className="kind-label">
                                                            {kinds[element.kind]}
                                                        </span>
                                                        <strong>
                                                            {element.text || element.id}
                                                        </strong>
                                                        <small>
                                                            {(element.actions ?? [])
                                                                .map((action) => actions[action])
                                                                .join(' · ') ||
                                                                'Lecture seule'}{' '}
                                                            · Observation
                                                        </small>
                                                    </span>
                                                    <span
                                                        className="confidence"
                                                        title="Score de confiance annoncé par le pipeline"
                                                    >
                                                        {Math.round(element.confidence * 100)} %
                                                    </span>
                                                </button>
                                            </li>
                                        ))}
                                    </ol>
                                    {result.data.ocr && (
                                        <section aria-label="Lecture des cartes">
                                            <h4>Lecture des cartes</h4>
                                            <p>Versions à vérifier avant ajout à l’inventaire.</p>
                                            <ul>
                                                {result.data.ocr.cards.map((card) => (
                                                    <li key={card.element_id}>
                                                        {card.reading
                                                            ? `${card.reading.name} · ${card.reading.rating}`
                                                            : 'Carte à relire'}
                                                        {' — '}
                                                        {card.issues.length
                                                            ? card.issues.join(' ; ')
                                                            : card.candidate_ids.length
                                                              ? `Versions candidates : ${card.candidate_ids.join(', ')}`
                                                              : 'Version absente du catalogue local'}
                                                    </li>
                                                ))}
                                            </ul>
                                            <OcrInventory
                                                key={result.data.capture_id}
                                                apiUrl={apiUrl}
                                                report={result.data.ocr}
                                            />
                                            {result.data.ocr.challenge_ready &&
                                                result.data.ocr.challenge && (
                                                    <button
                                                        onClick={() =>
                                                            onChallenge?.(
                                                                result.data.ocr!.challenge!,
                                                            )
                                                        }
                                                    >
                                                        Utiliser ces conditions dans le solveur
                                                    </button>
                                                )}
                                            {result.data.ocr.challenge_issues.length > 0 && (
                                                <p role="status">
                                                    Conditions incomplètes :{' '}
                                                    {result.data.ocr.challenge_issues.join(' ; ')}
                                                </p>
                                            )}
                                        </section>
                                    )}
                                    {selected && (
                                        <details className="analysis-coordinates">
                                            <summary>Coordonnées de l’élément sélectionné</summary>
                                            <p>
                                                x {selected.bbox.x} · y {selected.bbox.y} ·{' '}
                                                {selected.bbox.width} × {selected.bbox.height} px
                                            </p>
                                            {selection?.tab && !synthetic && (
                                                <ViewportPoint
                                                    capture={selection.tab}
                                                    box={selected.bbox}
                                                />
                                            )}
                                        </details>
                                    )}
                                    <details className="json-details">
                                        <summary>
                                            Voir le JSON {synthetic ? 'de l’exemple' : 'reçu'}
                                        </summary>
                                        <pre>{JSON.stringify(result.data, null, 2)}</pre>
                                    </details>
                                    <p className="model-caption">
                                        Source : {result.data.model_name}
                                    </p>
                                </>
                            )}
                        </>
                    ) : (
                        <div className="analysis-empty">
                            <div className="scan-stage" aria-hidden="true">
                                <div className="scan-stage-field" />
                                <div className="scan-stage-card">
                                    <StadiumIcon name="image" />
                                </div>
                                <div className="scan-stage-corners" />
                                <span className="scan-stage-caption">SBC / VISION</span>
                            </div>
                            <span className="analysis-empty-eyebrow">PRÊT À OBSERVER</span>
                            <h3 id="results-title">Les éléments apparaîtront ici</h3>
                            <p>
                                Choisis une capture. Retrouve ensuite les textes, les cartes et
                                leurs repères.
                            </p>
                            <div className="analysis-flow">
                                <span>CAPTURE</span>
                                <StadiumIcon name="arrow" />
                                <span>VISION</span>
                                <StadiumIcon name="arrow" />
                                <span>INFORMATIONS</span>
                            </div>
                        </div>
                    )}
                </section>
            </div>
        </section>
    );
}

function ClubScanPanel({
    apiUrl,
    connected,
    disabled,
    onRunning,
}: {
    apiUrl: string;
    connected: boolean;
    disabled: boolean;
    onRunning?: (running: boolean) => void;
}) {
    type Report = {
        source: 'dom';
        complete: boolean;
        pages: number;
        observed: number;
        identified: number;
        pending: number;
        loans: number;
        ocr_readable: number;
        ocr_matched: number;
        inventory_updated: boolean;
        expected_revision?: string;
        cards: Array<{
            reading: { name: string; element_id: string };
            candidate_ids: number[];
            loan: boolean;
        }>;
    };
    const [scan, setScan] = useState<ClubScan | null>(null);
    const [report, setReport] = useState<Report | null>(null);
    const [revision, setRevision] = useState('');
    const [message, setMessage] = useState('');
    const [limit, setLimit] = useState(100);
    const current = useRef<AbortController | null>(null);
    useEffect(
        () => () => {
            current.current?.abort();
            onRunning?.(false);
        },
        [onRunning],
    );
    async function run(confirm = false, saveOnly = false) {
        const controller = new AbortController();
        current.current = controller;
        onRunning?.(true);
        setMessage(confirm ? 'Enregistrement du comptage local…' : 'Préparation du scan…');
        try {
            let observation = scan,
                expected = revision;
            if (!confirm && !saveOnly) {
                setReport(null);
                setScan(null);
                const workspace = await loadWorkspace(apiUrl, controller.signal);
                if (workspace.mode !== 'local')
                    throw new Error(
                        'Configurer une base locale réelle, hors démo, avant le scan EA.',
                    );
                expected = workspace.revision;
                setRevision(expected);
                observation = await scanClub(apiUrl, controller.signal, setMessage, limit, setScan);
                setScan(observation);
            }
            const value = (await requestJson(
                apiUrl,
                '/api/v1/sbc/club-scan',
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        ...observation,
                        expected_revision: expected,
                        confirmed: confirm,
                    }),
                },
                controller.signal,
                15000,
            )) as Report;
            if (
                value.source !== 'dom' ||
                !Number.isSafeInteger(value.observed) ||
                !Array.isArray(value.cards)
            )
                throw new Error('Rapport de scan invalide.');
            setReport(value);
            if (value.expected_revision) setRevision(value.expected_revision);
            setMessage(
                confirm
                    ? 'Comptage local remplacé ; les cartes importées sont protégées.'
                    : 'Observations enregistrées sur le serveur.',
            );
        } catch (error) {
            setMessage(
                controller.signal.aborted
                    ? 'Scan arrêté. Les pages déjà lues peuvent être sauvegardées séparément.'
                    : error instanceof Error
                      ? error.message
                      : 'Scan impossible.',
            );
        } finally {
            current.current = null;
            onRunning?.(false);
        }
    }
    async function restore() {
        const controller = new AbortController();
        current.current = controller;
        onRunning?.(true);
        try {
            const saved = (await requestJson(
                apiUrl,
                '/api/v1/sbc/club-scan',
                {},
                controller.signal,
                15000,
            )) as { observation: ClubScan; report: Report; expected_revision: string };
            setScan(saved.observation);
            setReport(saved.report);
            setRevision(saved.expected_revision);
            setMessage('Dernier relevé restauré. Rescanner si le contenu du club a changé.');
        } catch (error) {
            setMessage(error instanceof Error ? error.message : 'Lecture impossible.');
        } finally {
            current.current = null;
            onRunning?.(false);
        }
    }
    return (
        <section className="panel" aria-label="Scan hybride du club">
            <h3>Scanner le club EA</h3>
            <p>
                Ouvrir la première page de « Club → Players ». Chaque page est capturée pour l’OCR,
                puis ses lignes HTML sont lues sans défilement. Seul le bouton « Next » est utilisé.
            </p>
            <label>
                Nombre maximal de pages{' '}
                <input
                    type="number"
                    min="1"
                    max="500"
                    value={limit}
                    disabled={!!current.current}
                    onChange={(e) => setLimit(Number(e.target.value))}
                />
            </label>
            <button disabled={!connected || disabled || !!current.current} onClick={() => run()}>
                Scanner le club depuis la première page
            </button>
            <button disabled={!connected || disabled || !!current.current} onClick={restore}>
                Rouvrir le dernier relevé
            </button>
            {!!current.current && (
                <button onClick={() => current.current?.abort()}>Arrêter le scan</button>
            )}
            {message && <p role="status">{message}</p>}
            {scan && !report && !current.current && (
                <button disabled={disabled} onClick={() => run(false, true)}>
                    Sauvegarder les pages déjà lues
                </button>
            )}
            {report && (
                <>
                    <p>
                        {report.pages} pages · {report.observed} cartes HTML · {report.ocr_readable}{' '}
                        lectures OCR exploitables ({report.ocr_matched} noms/notes concordent avec
                        le HTML visible) · {report.loans} prêts.
                    </p>
                    <p>
                        {report.identified} versions uniques utilisables ; {report.pending}{' '}
                        observations en attente ou en prêt.{' '}
                        {report.complete
                            ? 'Dernière page atteinte.'
                            : 'Scan partiel : le comptage du club est conservé.'}
                    </p>
                    <p>
                        La confirmation remplace le précédent comptage DOM. Les identifiants sont
                        locaux ; les copies identiques sont comptées par version. Toutes les cartes
                        importées sont protégées. Les copies saisies manuellement doivent être
                        rapprochées séparément.
                    </p>
                    <button
                        disabled={
                            disabled ||
                            !!current.current ||
                            !report.complete ||
                            !report.identified ||
                            report.inventory_updated
                        }
                        onClick={() => run(true)}
                    >
                        Confirmer les versions identifiées dans le club local
                    </button>
                    <details>
                        <summary>Joueurs observés et versions à vérifier</summary>
                        <ul>
                            {report.cards.map((c) => (
                                <li key={c.reading.element_id}>
                                    {c.reading.name} :{' '}
                                    {c.loan
                                        ? 'prêt, exclu des SBC'
                                        : c.candidate_ids.length
                                          ? c.candidate_ids.join(', ')
                                          : 'version absente du catalogue'}
                                </li>
                            ))}
                        </ul>
                    </details>
                </>
            )}
        </section>
    );
}

function OcrInventory({
    apiUrl,
    report,
}: {
    apiUrl: string;
    report: NonNullable<Perception['ocr']>;
}) {
    const [ids, setIds] = useState<Record<string, string>>({});
    const [versions, setVersions] = useState<Record<string, string>>({});
    const [message, setMessage] = useState('');
    const [saving, setSaving] = useState(false);
    const cards = report.cards.filter(
        (c) => c.reading && !c.issues.length && c.candidate_ids.length,
    );
    async function save() {
        setSaving(true);
        try {
            const controller = new AbortController();
            const workspace = await loadWorkspace(apiUrl, controller.signal);
            const choices = Object.fromEntries(
                cards
                    .filter(
                        (c) =>
                            ids[c.element_id]?.trim() &&
                            (versions[c.element_id] || c.candidate_ids.length === 1),
                    )
                    .map((c) => [
                        c.element_id,
                        {
                            instance_id: ids[c.element_id].trim(),
                            card_id: Number(versions[c.element_id] || c.candidate_ids[0]),
                            protected: true,
                        },
                    ]),
            );
            if (!Object.keys(choices).length)
                throw new Error('Choisir une version et un identifiant d’exemplaire.');
            await requestJson(
                apiUrl,
                '/api/v1/sbc/inventory',
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        expected_revision: workspace.revision,
                        report,
                        choices,
                        confirmed: true,
                    }),
                },
                controller.signal,
                15000,
            );
            setMessage('Lectures enregistrées dans le club local, avec protection activée.');
        } catch (error) {
            setMessage(error instanceof Error ? error.message : 'Enregistrement impossible.');
        } finally {
            setSaving(false);
        }
    }
    if (!cards.length) return null;
    return (
        <fieldset disabled={saving}>
            <legend>Confirmer les exemplaires du club local</legend>
            <p>
                Réutilise le même identifiant pour une carte déjà observée ; une autre copie doit
                avoir un autre identifiant.
            </p>
            {cards.map((card) => (
                <div key={card.element_id}>
                    <label>
                        {card.reading!.name} : identifiant de l’exemplaire
                        <input
                            value={ids[card.element_id] || ''}
                            onChange={(e) => setIds({ ...ids, [card.element_id]: e.target.value })}
                        />
                    </label>
                    <label>
                        Version vérifiée
                        <select
                            value={
                                versions[card.element_id] ||
                                (card.candidate_ids.length === 1 ? card.candidate_ids[0] : '')
                            }
                            onChange={(e) =>
                                setVersions({ ...versions, [card.element_id]: e.target.value })
                            }
                        >
                            <option value="">Choisir la version</option>
                            {card.candidate_ids.map((id) => (
                                <option key={id} value={id}>
                                    {id}
                                </option>
                            ))}
                        </select>
                    </label>
                </div>
            ))}
            <button onClick={save}>Confirmer l’ajout au club local</button>
            {message && <p role="status">{message}</p>}
        </fieldset>
    );
}

function ViewportPoint({
    capture,
    box,
}: {
    capture: TabCapture;
    box: Perception['elements'][number]['bbox'];
}) {
    const point = imagePointToViewport(capture, box);
    return (
        <small>
            Centre dans la page : x {point.x.toFixed(1)} · y {point.y.toFixed(1)} px CSS ·
            observation
        </small>
    );
}
