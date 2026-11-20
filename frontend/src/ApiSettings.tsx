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
    let address = 'Adresse à vérifier';
    try {
        address = new URL(apiUrl).host;
    } catch {
        /* Adresse en cours de saisie. */
    }
    return (
        <div className="settings-grid settings-workspace">
            <section className="panel settings-server" aria-labelledby="connection-title">
                <div className="settings-server-heading">
                    <span className="settings-server-icon">
                        <StadiumIcon name="server" />
                    </span>
                    <div>
                        <span className="settings-section-label">SERVEUR DU PROJET</span>
                        <h3 id="connection-title">Connecter l’API</h3>
                    </div>
                    <span className={`settings-state-tag ${connection ? 'is-connected' : ''}`}>
                        {checking ? 'Vérification…' : connection ? 'Connectée' : 'À vérifier'}
                    </span>
                </div>
                <div className="settings-server-address">
                    <span>VOTRE POINT DE CONNEXION</span>
                    <strong>{address}</strong>
                </div>
                <form
                    className="settings-connection-form"
                    noValidate
                    onSubmit={(event) => {
                        event.preventDefault();
                        if (!busy) void onConnect();
                    }}
                >
                    <div className="settings-field-heading">
                        <label className="field-label" htmlFor="api-url">
                            Adresse du serveur
                        </label>
                        <span>01</span>
                    </div>
                    <div className="settings-input-frame">
                        <StadiumIcon name="server" />
                        <input
                            id="api-url"
                            type="url"
                            spellCheck={false}
                            value={apiUrl}
                            disabled={busy}
                            onChange={(event) => onUrlChange(event.target.value)}
                            aria-describedby="api-url-hint"
                        />
                    </div>
                    <p className="field-hint" id="api-url-hint">
                        L’adresse est mémorisée sur cet appareil.
                    </p>
                    <div className="settings-field-heading api-key-label">
                        <label className="field-label" htmlFor="api-key">
                            Clé API (si demandée)
                        </label>
                        <span>02</span>
                    </div>
                    <div className="settings-input-frame">
                        <StadiumIcon name="lock" />
                        <input
                            id="api-key"
                            type="password"
                            autoComplete="off"
                            spellCheck={false}
                            value={apiKey}
                            disabled={busy}
                            onChange={(event) => onKeyChange(event.target.value)}
                            aria-describedby="api-key-hint"
                        />
                    </div>
                    <div className="settings-key-help">
                        <p className="field-hint" id="api-key-hint">
                            Pour cette session uniquement.
                        </p>
                        <button
                            className="text-button"
                            type="button"
                            disabled={busy || !apiKey}
                            onClick={() => onKeyChange('')}
                        >
                            Effacer la clé
                        </button>
                    </div>
                    <div className="stadium-action-row">
                        <button className="primary-button full-width" type="submit" disabled={busy}>
                            {checking ? 'Vérification en cours…' : 'Vérifier la connexion'}
                            <StadiumIcon name="arrow" />
                        </button>
                    </div>
                </form>
                <div className="settings-connection-result" role="status" aria-live="polite">
                    <span className={`status-dot ${connection ? 'connected' : ''}`} />
                    <span>
                        {checking
                            ? 'Connexion au serveur…'
                            : connection
                              ? `Serveur joignable · v${connection.version}`
                              : 'Connexion à vérifier'}
                    </span>
                </div>
                {connection && (
                    <div className={`settings-model-state ${visionReady ? 'ready' : ''}`}>
                        <StadiumIcon name="scan" />
                        <div>
                            <strong>
                                {visionReady ? 'Vision disponible' : 'Vision à raccorder'}
                            </strong>
                            <p>
                                {visionReady
                                    ? connection.ocr
                                        ? 'Détection et OCR annoncés par l’API.'
                                        : 'Détection annoncée par l’API. OCR non configuré.'
                                    : 'Le serveur répond ; aucun modèle prêt n’est annoncé.'}
                            </p>
                        </div>
                    </div>
                )}
            </section>
            <div className="settings-side">
                <details className="settings-disclosure settings-privacy">
                    <summary>
                        <span className="settings-small-icon">
                            <StadiumIcon name="lock" />
                        </span>
                        <span>
                            <strong>Votre session</strong>
                            <small>Ce qui reste sur cet appareil</small>
                        </span>
                        <span className="settings-chevron">
                            <StadiumIcon name="arrow" />
                        </span>
                    </summary>
                    <div className="settings-disclosure-body">
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
                            L’envoi d’une capture nécessite une action explicite. Le solveur reçoit
                            les informations structurées.
                        </p>
                    </div>
                </details>
                <details className="settings-disclosure settings-lab">
                    <summary>
                        <span className="settings-small-icon">
                            <StadiumIcon name="scan" />
                        </span>
                        <span>
                            <strong>Laboratoire du contrôleur</strong>
                            <small>Tests sur une page locale</small>
                        </span>
                        <span className="settings-chevron">
                            <StadiumIcon name="arrow" />
                        </span>
                    </summary>
                    <div className="settings-disclosure-body">
                        <p>
                            Observer les étapes du contrôleur et tester ses actions sur une page
                            locale avec des cartes fictives.
                        </p>
                        <button
                            className="secondary-button full-width"
                            onClick={onController}
                            disabled={busy}
                        >
                            Contrôleur local
                            <StadiumIcon name="arrow" />
                        </button>
                    </div>
                </details>
                <p className="settings-footnote">
                    <StadiumIcon name="lock" />
                    La clé reste en mémoire pour cette session uniquement.
                </p>
            </div>
        </div>
    );
}
