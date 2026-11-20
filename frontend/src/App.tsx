import { useEffect, useRef, useState, type ChangeEvent } from 'react';
import demoPayload from '../../data/fixtures/perception.synthetic.json';
import demoImage from '../../data/fixtures/perception.synthetic.png';
import SbcWorkspace from './SbcWorkspace';
import ApiSettings from './ApiSettings';
import PerceptionWorkspace, {
    type CaptureSelection as Selection,
    type PerceptionResult as Result,
} from './PerceptionWorkspace';
import { StadiumBrand, StadiumIcon } from './design-a1/StadiumKit';
import { clearSessionApiKey, setSessionApiKey } from './lib/api-key';
import ControllerWorkspace from './ControllerWorkspace';
import { nativeLabAdapter } from './lib/lab-adapter';
import { captureActiveTab } from './lib/tab-capture';
import {
    analyzeImage,
    ApiError,
    checkConnection,
    readImage,
    validatePerception,
    type Connection,
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

type Notice = { title: string; message: string; code?: string };

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
    const [workspace, setWorkspace] = useState<'perception' | 'sbc' | 'settings' | 'controller'>(
        () => (location.hash === '#connection-title' ? 'settings' : 'perception'),
    );
    const [controllerRunning, setControllerRunning] = useState(false);
    const [apiUrl, setApiUrl] = useState(DEFAULT_API_URL);
    const [apiKey, setApiKey] = useState('');
    const [apiSession, setApiSession] = useState(0);
    const [settingsReady, setSettingsReady] = useState(false);
    const [connection, setConnection] = useState<Connection | null>(null);
    const [selection, setSelection] = useState<Selection | null>(null);
    const [result, setResult] = useState<Result | null>(null);
    const [notice, setNotice] = useState<Notice | null>(null);
    const [busy, setBusy] = useState<'connection' | 'image' | 'capture' | 'analysis' | null>(null);
    const active = useRef<AbortController | null>(null);

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
            clearSessionApiKey();
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

    async function connect(): Promise<boolean> {
        let normalized: string;
        try {
            normalized = normalizeApiUrl(apiUrl);
            setSessionApiKey(normalized, apiKey);
        } catch (error) {
            setNotice(describeError(error, 'Connexion à corriger'));
            return false;
        }
        const controller = begin('connection');
        setConnection(null);
        try {
            await authorizeApi(normalized);
            if (active.current !== controller) return false;
            await saveApiUrl(normalized);
            const value = await checkConnection(normalized, controller.signal);
            if (active.current === controller) {
                setApiUrl(normalized);
                setConnection(value);
                return true;
            }
            return false;
        } catch (error) {
            if (active.current === controller)
                setNotice(describeError(error, 'Connexion impossible'));
            return false;
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

    async function captureTab() {
        const controller = begin('capture');
        setSelection(null);
        try {
            const tab = await captureActiveTab(controller.signal);
            if (active.current === controller) setSelection({ ...tab, tab });
            else URL.revokeObjectURL(tab.url);
        } catch (error) {
            if (active.current === controller)
                setNotice(describeError(error, 'Capture impossible'));
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

    const page = {
        perception: {
            kicker: 'VISION & LECTURE',
            title: 'ANALYSER UNE CAPTURE',
            description:
                'Capture ton onglet ou choisis une image pour examiner ce que la vision a lu.',
        },
        sbc: {
            kicker: 'CLUB & COMPOSITION',
            title: 'PRÉPARER SON ÉQUIPE',
            description: 'Retrouve les cartes, les conditions et le coût de la proposition.',
        },
        settings: {
            kicker: 'CONNEXION & SESSION',
            title: 'VOS RÉGLAGES',
            description: 'Configure le serveur du projet et vérifie sa disponibilité.',
        },
        controller: {
            kicker: 'LABORATOIRE',
            title: 'OBSERVER, AGIR, VÉRIFIER',
            description: 'Teste le contrôleur sur une page locale avec des cartes fictives.',
        },
    }[workspace];
    function navigate(next: typeof workspace) {
        setWorkspace(next);
        setNotice(null);
    }
    function changeUrl(value: string) {
        clearSessionApiKey();
        setApiKey('');
        setApiSession((previous) => previous + 1);
        setApiUrl(value);
        setConnection(null);
        setResult(null);
        setNotice(null);
    }
    function changeKey(value: string) {
        clearSessionApiKey();
        setApiKey(value);
        setApiSession((previous) => previous + 1);
        setConnection(null);
        setResult(null);
        setNotice(null);
    }

    return (
        <main className="app-shell stadium-kit stadium-app" data-workspace={workspace}>
            <header className="app-header stadium-header">
                <StadiumBrand />
                <div className="header-actions">
                    <button
                        className="phase-badge"
                        onClick={() => navigate('settings')}
                        disabled={!!busy || controllerRunning}
                        aria-label="Ouvrir les réglages de connexion"
                        aria-describedby="header-api-state"
                        title={
                            connection ? 'API connectée · Réglages' : 'API à configurer · Réglages'
                        }
                    >
                        <span className={`status-dot ${connection ? 'connected' : ''}`} />
                        <span id="header-api-state">
                            {connection ? 'API connectée' : 'API à configurer'}
                        </span>
                    </button>
                    {isExtension() && (
                        <button
                            className="header-icon-button"
                            aria-label="Ouvrir dans un onglet"
                            title="Ouvrir dans un onglet"
                            onClick={() =>
                                openWorkspace().catch((error) =>
                                    setNotice(describeError(error, 'Ouverture impossible')),
                                )
                            }
                        >
                            <StadiumIcon name="expand" />
                        </button>
                    )}
                    {isExtension() &&
                        new URLSearchParams(location.search).get('view') === 'popup' && (
                            <button
                                className="header-icon-button header-close-button"
                                type="button"
                                aria-label="Fermer le popup"
                                title="Fermer le popup"
                                disabled={!!busy || controllerRunning}
                                onClick={() => window.close()}
                            >
                                <StadiumIcon name="close" />
                            </button>
                        )}
                </div>
            </header>
            <nav className="workspace-nav main-nav" aria-label="Espace de travail">
                <button
                    type="button"
                    aria-pressed={workspace === 'perception'}
                    onClick={() => navigate('perception')}
                    disabled={!!busy || controllerRunning}
                >
                    Analyser
                </button>
                <button
                    type="button"
                    aria-pressed={workspace === 'sbc'}
                    onClick={() => navigate('sbc')}
                    disabled={!!busy || controllerRunning}
                >
                    Équipe
                </button>
                <button
                    type="button"
                    aria-pressed={workspace === 'settings' || workspace === 'controller'}
                    onClick={() => navigate('settings')}
                    disabled={!!busy || controllerRunning}
                >
                    Réglages
                </button>
            </nav>
            <div className="app-page">
                <div className="intro">
                    <p className="page-kicker">{page.kicker}</p>
                    <h1>{page.title}</h1>
                    <p>{page.description}</p>
                </div>
                {(busy || notice) && (
                    <section className="page-feedback" aria-label="État de l’opération">
                        {busy && (
                            <div className="busy-notice" role="status">
                                <span className="spinner" aria-hidden="true" />
                                <span>
                                    {busy === 'connection'
                                        ? 'Connexion au serveur…'
                                        : busy === 'image'
                                          ? 'Lecture de l’image…'
                                          : busy === 'capture'
                                            ? 'Capture de la zone visible…'
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
                    </section>
                )}
                <div hidden={workspace !== 'settings'}>
                    <ApiSettings
                        apiUrl={apiUrl}
                        apiKey={apiKey}
                        connection={connection}
                        busy={!!busy || !settingsReady || controllerRunning}
                        checking={busy === 'connection'}
                        onUrlChange={changeUrl}
                        onKeyChange={changeKey}
                        onConnect={connect}
                        onController={() => navigate('controller')}
                    />
                </div>
                <div hidden={workspace !== 'perception'}>
                    <PerceptionWorkspace
                        selection={selection}
                        result={result}
                        connected={!!connection}
                        busy={busy}
                        onChoose={chooseFile}
                        onCapture={captureTab}
                        onAnalyze={analyze}
                        onExample={showExample}
                        onSettings={() => navigate('settings')}
                        onClear={() => {
                            setSelection(null);
                            setResult(null);
                            setNotice(null);
                        }}
                    />
                </div>
                <div hidden={workspace !== 'sbc'}>
                    <SbcWorkspace
                        key={apiSession}
                        apiUrl={apiUrl}
                        connected={!!connection}
                        onConnect={connect}
                    />
                </div>
                {workspace === 'controller' && (
                    <div>
                        <button
                            className="text-button lab-back"
                            onClick={() => navigate('settings')}
                            disabled={controllerRunning}
                        >
                            ← Retour aux réglages
                        </button>
                        <ControllerWorkspace
                            makeAdapter={nativeLabAdapter}
                            native
                            enabled={isExtension()}
                            apiUrl={apiUrl}
                            beforeApiStart={connection ? undefined : connect}
                            onRunning={setControllerRunning}
                        />
                    </div>
                )}
                <footer className="app-footer">
                    <span>Epitech 2026–2027</span>
                    <span>
                        {workspace === 'perception'
                            ? 'Étape 1 · Perception de l’interface'
                            : workspace === 'sbc'
                              ? 'Étape 2 · Lecture des propositions'
                              : workspace === 'settings'
                                ? 'Connexion & session'
                                : 'Laboratoire du contrôleur'}
                    </span>
                </footer>
            </div>
        </main>
    );
}
