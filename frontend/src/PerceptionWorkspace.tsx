import { useRef, useState, type ChangeEvent } from 'react';
import { StadiumIcon } from './design-a1/StadiumKit';
import { isExtension } from './lib/platform';
import { imagePointToViewport, type TabCapture } from './lib/tab-capture';
import type { ElementKind, Perception } from './lib/api';

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
