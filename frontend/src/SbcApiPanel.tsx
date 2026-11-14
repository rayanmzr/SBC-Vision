import { useEffect, useMemo, useRef, useState } from 'react';
import { normalizeApiUrl } from './lib/platform';
import { ApiError } from './lib/api';
import { credits } from './lib/sbc-report';
import {
    loadWorkspace,
    updateProtection,
    solveWorkspace,
    type ApiProposal,
    type Workspace,
} from './lib/sbc-api';

type Props = {
    apiUrl: string;
    connected: boolean;
    active: boolean;
    onConnect: () => Promise<boolean>;
    onStart: () => number;
    onReport: (proposal: ApiProposal, token: number) => void;
    onReset: () => void;
};

export default function SbcApiPanel({
    apiUrl,
    connected,
    active,
    onConnect,
    onStart,
    onReport,
    onReset,
}: Props) {
    const [workspace, setWorkspace] = useState<Workspace | null>(null);
    const [budget, setBudget] = useState('');
    const [operation, setOperation] = useState<'load' | 'save' | 'solve' | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [saved, setSaved] = useState(false);
    const [visible, setVisible] = useState(50);
    const current = useRef<AbortController | null>(null);
    const base = useMemo(() => {
        try {
            return normalizeApiUrl(apiUrl);
        } catch {
            return apiUrl;
        }
    }, [apiUrl]);

    useEffect(() => {
        current.current?.abort();
        current.current = null;
        setWorkspace(null);
        setOperation(null);
        setError(null);
        setSaved(false);
        onReset();
        return () => {
            current.current?.abort();
            current.current = null;
        };
    }, [base, active, onReset]);

    function begin(type: NonNullable<typeof operation>) {
        current.current?.abort();
        const controller = new AbortController();
        current.current = controller;
        setOperation(type);
        setError(null);
        setSaved(false);
        return { controller, token: onStart() };
    }
    function finish(controller: AbortController) {
        if (current.current === controller) {
            current.current = null;
            setOperation(null);
        }
    }
    function failed(failure: unknown, controller: AbortController) {
        if (current.current !== controller) return;
        setWorkspace(null);
        const message =
            failure instanceof Error ? failure.message : 'L’opération n’a pas pu être confirmée.';
        setError(
            `${message}${failure instanceof ApiError && failure.status ? ` (HTTP ${failure.status})` : ''} Recharger l’inventaire avant de continuer.`,
        );
    }
    async function load() {
        const { controller } = begin('load');
        try {
            if (!connected && !(await onConnect()))
                throw new Error(
                    'Connexion non confirmée. Vérifier l’adresse et la clé dans Réglages.',
                );
            if (current.current !== controller) return;
            const data = await loadWorkspace(base, controller.signal);
            if (current.current === controller) {
                setWorkspace(data);
                setBudget(String(data.challenge?.budget ?? 0));
                setVisible(50);
            }
        } catch (failure) {
            failed(failure, controller);
        } finally {
            finish(controller);
        }
    }
    async function protect(key: string, value: boolean) {
        if (!workspace) return;
        const { controller } = begin('save');
        try {
            const updated = await updateProtection(base, workspace, key, value, controller.signal);
            if (current.current === controller) {
                setWorkspace(updated);
                setSaved(true);
            }
        } catch (failure) {
            failed(failure, controller);
        } finally {
            finish(controller);
        }
    }
    async function calculate() {
        if (!workspace) return;
        const { controller, token } = begin('solve');
        try {
            const proposal = await solveWorkspace(
                base,
                workspace,
                Number(budget),
                controller.signal,
            );
            if (current.current === controller) onReport(proposal, token);
        } catch (failure) {
            failed(failure, controller);
        } finally {
            finish(controller);
        }
    }
    function cancel() {
        current.current?.abort();
        current.current = null;
        setOperation(null);
        setWorkspace(null);
        setError('Opération annulée. Recharger l’inventaire pour confirmer l’état actuel.');
    }

    const validBudget =
        budget.trim() !== '' &&
        Number.isSafeInteger(Number(budget)) &&
        Number(budget) >= 0 &&
        Number(budget) <= 1_000_000_000;
    return (
        <section className="panel api-workspace-panel" aria-labelledby="api-workspace-title">
            <div className="report-section-heading">
                <h3 id="api-workspace-title">Inventaire depuis l’API</h3>
                <button className="secondary-button" onClick={load} disabled={!!operation}>
                    {operation === 'load' ? 'Chargement…' : 'Charger l’inventaire'}
                </button>
            </div>
            <p className="field-hint">Serveur configuré : {apiUrl}</p>
            {!workspace && !operation && !error && (
                <div className="squad-empty-state">
                    <div className="squad-empty-art" aria-hidden="true">
                        <i />
                        <i />
                        <i />
                    </div>
                    <h4>Votre club commence ici</h4>
                    <p>Charge les cartes du serveur pour préparer une proposition.</p>
                </div>
            )}
            {error && (
                <div className="notice" role="alert">
                    <strong>État à recharger</strong>
                    <p>{error}</p>
                </div>
            )}
            {operation && (
                <div className="busy-notice" role="status">
                    <span className="spinner" aria-hidden="true" />
                    <span>
                        {operation === 'solve'
                            ? 'Calcul CP-SAT sur le serveur…'
                            : operation === 'save'
                              ? 'Enregistrement de la protection…'
                              : 'Lecture de l’inventaire…'}
                    </span>
                    <button className="text-button" onClick={cancel}>
                        Annuler l’opération API
                    </button>
                </div>
            )}
            {workspace && (
                <>
                    <div
                        className={workspace.mode === 'demo' ? 'synthetic-notice' : 'import-notice'}
                    >
                        <strong>
                            {workspace.mode === 'demo'
                                ? 'API de démonstration · Cartes fictives, calcul réel'
                                : 'Inventaire local confirmé dans la base'}
                        </strong>
                        <p>
                            {workspace.items.length} exemplaires. Les protections sont enregistrées
                            sur ce serveur.
                        </p>
                    </div>
                    <div className="server-inventory">
                        {workspace.items.slice(0, visible).map((card) => (
                            <div className="server-item" key={card.key}>
                                <span className="rating-token">{card.rating}</span>
                                <div className="server-item-name">
                                    <strong>{card.name}</strong>
                                    <small>
                                        {card.positions.join(' / ')} · version {card.card_id}
                                    </small>
                                    <small>{credits(card.value)}</small>
                                    <small className="candidate-key">{card.key}</small>
                                </div>
                                <label className="server-protection">
                                    <input
                                        type="checkbox"
                                        aria-label={`Protection du serveur : ${card.key}`}
                                        checked={!!card.protected}
                                        disabled={!!operation}
                                        onChange={(event) =>
                                            protect(card.key, event.target.checked)
                                        }
                                    />
                                    {card.protected ? 'Protégée' : 'Utilisable'}
                                </label>
                            </div>
                        ))}
                    </div>
                    {visible < workspace.items.length && (
                        <button
                            className="text-button"
                            onClick={() => setVisible((value) => value + 50)}
                        >
                            Afficher 50 exemplaires supplémentaires
                        </button>
                    )}
                    {saved && (
                        <p className="saved-preference" role="status">
                            Protection enregistrée. Calculer une nouvelle proposition.
                        </p>
                    )}
                    {workspace.challenge ? (
                        <div className="api-solver-controls">
                            <label>
                                Budget d’achat
                                <input
                                    aria-label="Budget d’achat pour le solveur API"
                                    type="number"
                                    min="0"
                                    max="1000000000"
                                    step="1"
                                    value={budget}
                                    disabled={!!operation}
                                    onChange={(event) => {
                                        setBudget(event.target.value);
                                        onReset();
                                    }}
                                />
                            </label>
                            <button
                                className="primary-button"
                                onClick={calculate}
                                disabled={!!operation || !validBudget}
                            >
                                Calculer une proposition
                            </button>
                            <p className="field-hint">
                                {workspace.challenge.max_card_value != null
                                    ? `Plafond par carte : ${credits(workspace.challenge.max_card_value)}. `
                                    : ''}
                                Le budget concerne uniquement les achats.
                            </p>
                        </div>
                    ) : (
                        <div className="notice pending-notice" role="status">
                            <strong>Conditions à confirmer</strong>
                            <p>
                                {workspace.challenge_issues.join(' ') ||
                                    'Aucun défi disponible sur le serveur.'}
                            </p>
                        </div>
                    )}
                </>
            )}
        </section>
    );
}
