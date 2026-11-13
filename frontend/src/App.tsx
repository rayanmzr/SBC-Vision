import { useEffect, useRef, useState, type ChangeEvent } from 'react';
import demoPayload from '../../data/fixtures/perception.synthetic.json';
import demoImage from '../../data/fixtures/perception.synthetic.png';
import SbcWorkspace from './SbcWorkspace';
import {
    analyzeImage,
    ApiError,
    checkConnection,
    readImage,
    validatePerception,
    type Connection,
    type ElementKind,
    type Perception,
} from './lib/api';
import {
    authorizeApi,
    DEFAULT_API_URL,
    isExtension,
    loadApiUrl,
    normalizeApiUrl,
    openWorkspace,
    saveApiUrl,
} from './lib/platform';

type Selection = { file: File; url: string; width: number; height: number };
type Result = { data: Perception; source: 'api' | 'synthetic'; imageUrl: string };
type Notice = { title: string; message: string; code?: string };
const KIND_LABELS: Record<ElementKind, string> = {
    button: 'Bouton',
    input: 'Champ',
    link: 'Lien',
    menu: 'Menu',
    checkbox: 'Case à cocher',
    card: 'Carte',
    slot: 'Emplacement',
    text: 'Texte',
};
const ACTION_LABELS = { click: 'Clic', fill: 'Saisie', select: 'Sélection', scroll: 'Défilement' };

function FrameIcon() {
    return (
        <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.7"
            aria-hidden="true"
        >
            <path d="M8 3H3v5M16 3h5v5M21 16v5h-5M8 21H3v-5" />
            <path d="m7.5 12 3 3 6-6" />
        </svg>
    );
}

function describeError(error: unknown, context: string): Notice {
    if (error instanceof ApiError && error.code === 'perception_unavailable') {
        return {
            title: 'La vision reste à raccorder',
            message:
                'L’API a validé l’image, mais son pipeline de détection et d’OCR n’est pas encore configuré.',
            code: 'HTTP 503 · perception_unavailable',
        };
    }
    return {
        title:
            error instanceof ApiError && error.code === 'cancelled' ? 'Opération annulée' : context,
        message: error instanceof Error ? error.message : 'Une erreur inattendue est survenue.',
        code:
            error instanceof ApiError
                ? `${error.status ? `HTTP ${error.status} · ` : ''}${error.code}`
                : undefined,
    };
}

export default function App() {
    const [workspace, setWorkspace] = useState<'perception' | 'sbc'>('perception');
    const [apiUrl, setApiUrl] = useState(DEFAULT_API_URL);
    const [settingsReady, setSettingsReady] = useState(false);
    const [connection, setConnection] = useState<Connection | null>(null);
    const [selection, setSelection] = useState<Selection | null>(null);
    const [result, setResult] = useState<Result | null>(null);
    const [notice, setNotice] = useState<Notice | null>(null);
    const [busy, setBusy] = useState<'connection' | 'image' | 'analysis' | null>(null);
    const active = useRef<AbortController | null>(null);
    const fileInput = useRef<HTMLInputElement>(null);

    useEffect(() => {
        let mounted = true;
        loadApiUrl()
            .then((value) => {
                if (mounted) setApiUrl(value);
            })
            .catch(() => {
                if (mounted)
                    setNotice({
                        title: 'Réglages non restaurés',
                        message: 'L’adresse locale par défaut est utilisée.',
                    });
            })
            .finally(() => {
                if (mounted) setSettingsReady(true);
            });
        return () => {
            mounted = false;
            active.current?.abort();
            active.current = null;
        };
    }, []);

    useEffect(
        () => () => {
            if (selection) URL.revokeObjectURL(selection.url);
        },
        [selection],
    );

    function begin(operation: NonNullable<typeof busy>) {
        active.current?.abort();
        const controller = new AbortController();
        active.current = controller;
        setBusy(operation);
        setNotice(null);
        setResult(null);
        return controller;
    }

    function finish(controller: AbortController) {
        if (active.current === controller) {
            active.current = null;
            setBusy(null);
        }
    }

    function cancel() {
        active.current?.abort();
        active.current = null;
        setBusy(null);
        setNotice({
            title: 'Opération annulée',
            message: 'Tu peux réessayer ou choisir une autre image.',
        });
    }

    async function connect() {
        let normalized: string;
        try {
            normalized = normalizeApiUrl(apiUrl);
        } catch (error) {
            setNotice(describeError(error, 'Adresse à corriger'));
            return;
        }
        const controller = begin('connection');
        setConnection(null);
        try {
            await authorizeApi(normalized);
            if (active.current !== controller) return;
            await saveApiUrl(normalized);
            const value = await checkConnection(normalized, controller.signal);
            if (active.current === controller) {
                setApiUrl(normalized);
                setConnection(value);
            }
        } catch (error) {
            if (active.current === controller)
                setNotice(describeError(error, 'Connexion impossible'));
        } finally {
            finish(controller);
        }
    }

    async function chooseFile(event: ChangeEvent<HTMLInputElement>) {
        const file = event.target.files?.[0];
        event.target.value = '';
        if (!file) return;
        const controller = begin('image');
        setSelection(null);
        try {
            const image = await readImage(file);
            if (active.current === controller) setSelection({ file, ...image });
            else URL.revokeObjectURL(image.url);
        } catch (error) {
            if (active.current === controller)
                setNotice(describeError(error, 'Image inutilisable'));
        } finally {
            finish(controller);
        }
    }

    async function analyze() {
        if (!selection || !connection) return;
        const current = selection;
        const controller = begin('analysis');
        try {
            const data = await analyzeImage(apiUrl, current.file, current, controller.signal);
            if (active.current === controller)
                setResult({ data, source: 'api', imageUrl: current.url });
        } catch (error) {
            if (active.current === controller)
                setNotice(describeError(error, 'Analyse interrompue'));
        } finally {
            finish(controller);
        }
    }

    function showExample() {
        setSelection(null);
        setNotice(null);
        setResult({
            data: validatePerception(demoPayload),
            source: 'synthetic',
            imageUrl: demoImage,
        });
    }

    const preview = result?.imageUrl ?? selection?.url;
    const synthetic = result?.source === 'synthetic';
    const visionReady = connection?.modelLoaded && connection.perception;

    return (
        <main className="app-shell">
            <header className="app-header">
                <div className="brand">
                    <span className="brand-mark">
                        <FrameIcon />
                    </span>
                    <div>
                        <p className="eyebrow">PROJET COMPUTER VISION</p>
                        <h1>
                            SBC Vision<span className="version-tag">0.1</span>
                        </h1>
                    </div>
                </div>
                <div className="header-actions">
                    <span className="phase-badge">Observation manuelle</span>
                    {isExtension() && (
                        <button
                            className="text-button"
                            onClick={() =>
                                openWorkspace().catch((error) =>
                                    setNotice(describeError(error, 'Ouverture impossible')),
                                )
                            }
                        >
                            Ouvrir dans un onglet ↗
                        </button>
                    )}
                </div>
            </header>

            <div className="intro">
                <h2>
                    {workspace === 'perception'
                        ? 'Une image. Des informations exploitables.'
                        : 'Comprendre la composition proposée.'}
                </h2>
                <p>
                    {workspace === 'perception'
                        ? 'Connecte l’API, choisis une capture et examine les éléments qu’elle renvoie.'
                        : 'Examine les cartes, les conditions et les coûts transmis par le moteur SBC.'}
                </p>
            </div>

            <nav className="workspace-nav" aria-label="Espace de travail">
                <button
                    type="button"
                    aria-pressed={workspace === 'perception'}
                    onClick={() => setWorkspace('perception')}
                    disabled={!!busy}
                >
                    Analyse d’image
                </button>
                <button
                    type="button"
                    aria-pressed={workspace === 'sbc'}
                    onClick={() => setWorkspace('sbc')}
                    disabled={!!busy}
                >
                    Composition SBC
                </button>
            </nav>
            <div hidden={workspace !== 'perception'}>
                <div className="app-grid">
                    <aside className="controls">
                        <section className="panel" aria-labelledby="connection-title">
                            <div className="section-heading">
                                <span className="step">01</span>
                                <h3 id="connection-title">Connecter l’API</h3>
                            </div>
                            <label className="field-label" htmlFor="api-url">
                                Adresse du serveur
                            </label>
                            <input
                                id="api-url"
                                type="url"
                                spellCheck={false}
                                value={apiUrl}
                                disabled={!!busy || !settingsReady}
                                onChange={(event) => {
                                    setApiUrl(event.target.value);
                                    setConnection(null);
                                    setResult(null);
                                    setNotice(null);
                                }}
                            />
                            <p className="field-hint">L’adresse est mémorisée sur cet appareil.</p>
                            <button
                                className="secondary-button full-width"
                                onClick={connect}
                                disabled={!!busy || !settingsReady}
                            >
                                {busy === 'connection'
                                    ? 'Vérification en cours…'
                                    : 'Vérifier la connexion'}
                            </button>
                            <div className="connection-status" role="status" aria-live="polite">
                                <span className={`status-dot ${connection ? 'connected' : ''}`} />
                                <span>
                                    {connection
                                        ? `Serveur joignable · v${connection.version}`
                                        : 'Connexion à vérifier'}
                                </span>
                            </div>
                            {connection && (
                                <div className={`model-status ${visionReady ? 'ready' : ''}`}>
                                    <span>
                                        {visionReady ? 'Vision disponible' : 'Vision à raccorder'}
                                    </span>
                                    <small>
                                        {visionReady
                                            ? connection.ocr
                                                ? 'Détection et OCR annoncés par l’API'
                                                : 'Détection annoncée par l’API'
                                            : 'Le serveur répond ; aucun modèle prêt n’est annoncé.'}
                                    </small>
                                </div>
                            )}
                        </section>

                        <section className="panel" aria-labelledby="image-title">
                            <div className="section-heading">
                                <span className="step">02</span>
                                <h3 id="image-title">Choisir une capture</h3>
                            </div>
                            <input
                                ref={fileInput}
                                id="capture-file"
                                className="visually-hidden"
                                type="file"
                                accept="image/png,image/jpeg"
                                aria-label="Choisir une image PNG ou JPEG"
                                onChange={chooseFile}
                                disabled={!!busy}
                            />
                            <button
                                className="file-picker"
                                onClick={() => fileInput.current?.click()}
                                disabled={!!busy}
                            >
                                <span className="file-icon">
                                    <FrameIcon />
                                </span>
                                <strong>
                                    {selection ? 'Changer l’image' : 'Choisir une image'}
                                </strong>
                                <span>PNG ou JPEG · 5 Mio maximum</span>
                            </button>
                            {selection && (
                                <div className="file-info">
                                    <strong>{selection.file.name}</strong>
                                    <span>
                                        {selection.width} × {selection.height} px ·{' '}
                                        {(selection.file.size / 1024).toFixed(1)} Kio
                                    </span>
                                </div>
                            )}
                            <button
                                className="primary-button full-width"
                                onClick={analyze}
                                disabled={!selection || !connection || !!busy}
                            >
                                {busy === 'analysis' ? 'Analyse en cours…' : 'Envoyer à l’API'}
                                <span aria-hidden="true">↗</span>
                            </button>
                            <p className="field-hint">
                                L’envoi commence uniquement avec ce bouton.
                            </p>
                            <div className="example-choice">
                                <span>Pour découvrir l’affichage</span>
                                <button
                                    className="text-button"
                                    onClick={showExample}
                                    disabled={!!busy}
                                >
                                    Voir un exemple synthétique →
                                </button>
                            </div>
                        </section>
                    </aside>

                    <section className="panel results-panel" aria-labelledby="results-title">
                        <div className="section-heading result-heading">
                            <span className="step">03</span>
                            <h3 id="results-title">Examiner le résultat</h3>
                            {result && (
                                <span className={`source-badge ${synthetic ? 'synthetic' : ''}`}>
                                    {synthetic ? 'EXEMPLE FICTIF' : 'RÉPONSE API'}
                                </span>
                            )}
                        </div>
                        {busy && (
                            <div className="busy-notice" role="status">
                                <span className="spinner" aria-hidden="true" />
                                <span>
                                    {busy === 'connection'
                                        ? 'Connexion au serveur…'
                                        : busy === 'image'
                                          ? 'Lecture de l’image…'
                                          : 'L’API analyse la capture…'}
                                </span>
                                <button className="text-button" onClick={cancel}>
                                    Annuler
                                </button>
                            </div>
                        )}
                        {notice && (
                            <div
                                className={`notice ${notice.code?.includes('perception_unavailable') ? 'pending-notice' : ''}`}
                                role="alert"
                            >
                                <strong>{notice.title}</strong>
                                <p>{notice.message}</p>
                                {notice.code && <code>{notice.code}</code>}
                            </div>
                        )}
                        {synthetic && (
                            <div className="synthetic-notice">
                                <strong>Exemple synthétique · Données fictives</strong>
                                <p>
                                    Cette image et ces rectangles ont été préparés pour le
                                    développement. Ils ne sont pas issus d’une analyse par le
                                    modèle.
                                </p>
                            </div>
                        )}

                        {preview ? (
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
                                        role="img"
                                    >
                                        {result.data.elements.map((element, index) => (
                                            <g key={element.id}>
                                                <rect
                                                    x={element.bbox.x}
                                                    y={element.bbox.y}
                                                    width={element.bbox.width}
                                                    height={element.bbox.height}
                                                    vectorEffect="non-scaling-stroke"
                                                >
                                                    <title>
                                                        {KIND_LABELS[element.kind]} :{' '}
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
                        ) : (
                            <div className="empty-state">
                                <div className="empty-illustration">
                                    <FrameIcon />
                                </div>
                                <h4>Les éléments apparaîtront ici</h4>
                                <p>
                                    Choisis une capture pour afficher son aperçu, puis envoie-la au
                                    serveur pour obtenir son JSON.
                                </p>
                                <div className="flow-label">
                                    <span>IMAGE</span>
                                    <i>→</i>
                                    <span>API VISION</span>
                                    <i>→</i>
                                    <span>JSON</span>
                                </div>
                            </div>
                        )}

                        {result && (
                            <div className="result-content">
                                <div className="result-summary">
                                    <h4>
                                        {result.data.elements.length} élément
                                        {result.data.elements.length !== 1 ? 's' : ''}
                                    </h4>
                                    <span>
                                        {result.data.image.width} × {result.data.image.height} px
                                    </span>
                                </div>
                                {result.data.elements.length === 0 && (
                                    <p className="empty-detection">
                                        L’analyse a réussi, mais aucun élément n’a été détecté.
                                    </p>
                                )}
                                <ol className="element-list">
                                    {result.data.elements.map((element, index) => (
                                        <li key={element.id}>
                                            <span className="element-number">{index + 1}</span>
                                            <div className="element-description">
                                                <div>
                                                    <span className="kind-label">
                                                        {KIND_LABELS[element.kind]}
                                                    </span>
                                                    <strong>{element.text || element.id}</strong>
                                                </div>
                                                <small>
                                                    x {element.bbox.x} · y {element.bbox.y} ·{' '}
                                                    {element.bbox.width} × {element.bbox.height} px
                                                </small>
                                                <span className="element-actions">
                                                    {(element.actions ?? [])
                                                        .map((action) => ACTION_LABELS[action])
                                                        .join(' · ') || 'Lecture seule'}
                                                </span>
                                            </div>
                                            <span
                                                className="confidence"
                                                title="Score de confiance annoncé par le pipeline"
                                            >
                                                {Math.round(element.confidence * 100)} %
                                            </span>
                                        </li>
                                    ))}
                                </ol>
                                <details className="json-details">
                                    <summary>
                                        Voir le JSON {synthetic ? 'de l’exemple' : 'reçu'}
                                    </summary>
                                    <pre>{JSON.stringify(result.data, null, 2)}</pre>
                                </details>
                                <p className="model-caption">Source : {result.data.model_name}</p>
                            </div>
                        )}
                    </section>
                </div>
            </div>
            <div hidden={workspace !== 'sbc'}>
                <SbcWorkspace />
            </div>
            <footer className="app-footer">
                <span>Epitech 2026–2027</span>
                <span>
                    {workspace === 'perception'
                        ? 'Étape 1 · Perception de l’interface'
                        : 'Étape 2 · Lecture des propositions'}
                </span>
            </footer>
        </main>
    );
}
