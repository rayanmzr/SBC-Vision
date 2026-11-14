import type { Connection } from './lib/api';
import { StadiumIcon } from './design-a1/StadiumKit';

type Props = {
    apiUrl: string;
    apiKey: string;
    connection: Connection | null;
    busy: boolean;
    checking: boolean;
    onUrlChange: (value: string) => void;
    onKeyChange: (value: string) => void;
    onConnect: () => Promise<boolean>;
    onController: () => void;
};

export default function ApiSettings({
    apiUrl,
    apiKey,
    connection,
    busy,
    checking,
    onUrlChange,
    onKeyChange,
    onConnect,
    onController,
}: Props) {
    const visionReady = connection?.modelLoaded && connection.perception;
    return (
        <div className="settings-grid">
            <section className="panel settings-server" aria-labelledby="connection-title">
                <div className="section-heading">
                    <span className="step">
                        <StadiumIcon name="scan" />
                    </span>
                    <div>
                        <h3 id="connection-title">Connecter l’API</h3>
                    </div>
                </div>
                <label className="field-label" htmlFor="api-url">
                    Adresse du serveur
                </label>
                <input
                    id="api-url"
                    type="url"
                    spellCheck={false}
                    value={apiUrl}
                    disabled={busy}
                    onChange={(event) => onUrlChange(event.target.value)}
                />
                <p className="field-hint">L’adresse est mémorisée sur cet appareil.</p>
                <label className="field-label api-key-label" htmlFor="api-key">
                    Clé API (si demandée)
                </label>
                <input
                    id="api-key"
                    type="password"
                    autoComplete="off"
                    spellCheck={false}
                    value={apiKey}
                    disabled={busy}
                    onChange={(event) => onKeyChange(event.target.value)}
                />
                <p className="field-hint">Clé gardée pour cette session uniquement.</p>
                <button className="primary-button full-width" onClick={onConnect} disabled={busy}>
                    {checking ? 'Vérification en cours…' : 'Vérifier la connexion'}
                    <StadiumIcon name="arrow" />
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
                        <span>{visionReady ? 'Vision disponible' : 'Vision à raccorder'}</span>
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
            <div className="settings-side">
                <section className="panel" aria-labelledby="session-title">
                    <div className="section-heading">
                        <span className="step">01</span>
                        <h3 id="session-title">Votre session</h3>
                    </div>
                    <dl className="settings-retention">
                        <div>
                            <dt>Adresse API</dt>
                            <dd>Sur cet appareil</dd>
                        </div>
                        <div>
                            <dt>Clé d’accès</dt>
                            <dd>En mémoire, pour cette session</dd>
                        </div>
                        <div>
                            <dt>Captures et résultats</dt>
                            <dd>En mémoire dans l’extension</dd>
                        </div>
                    </dl>
                    <p className="field-hint">
                        La capture est envoyée au serveur uniquement avec le bouton d’analyse. Le
                        solveur utilise les informations structurées.
                    </p>
                </section>
                <section className="panel settings-lab" aria-labelledby="lab-settings-title">
                    <div className="section-heading">
                        <span className="step">02</span>
                        <h3 id="lab-settings-title">Laboratoire du contrôleur</h3>
                    </div>
                    <p>
                        Observer les étapes du contrôleur et tester ses actions sur une page locale
                        avec des cartes fictives.
                    </p>
                    <button
                        className="secondary-button full-width"
                        onClick={onController}
                        disabled={busy}
                    >
                        Contrôleur local
                        <StadiumIcon name="arrow" />
                    </button>
                </section>
            </div>
        </div>
    );
}
