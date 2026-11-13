import { useEffect, useRef, useState } from 'react';
import {
    runController,
    type ControllerAdapter,
    type Entry,
    type Mode,
    type RunResult,
} from './lib/controller';

const STATUS: Record<RunResult['status'], string> = {
    observed: 'Observation terminée · Aucun clic',
    simulated: 'Simulation terminée · Aucun clic',
    completed: 'Parcours local vérifié',
    step_limit: 'Budget atteint · Parcours incomplet',
    diverged: 'Divergence · Contrôleur arrêté',
    cancelled: 'Parcours interrompu',
    failed: 'Vérification impossible · Contrôleur arrêté',
};

export default function ControllerPanel({
    adapter,
    enabled = true,
    native = false,
    onRunning,
}: {
    adapter: ControllerAdapter;
    enabled?: boolean;
    native?: boolean;
    onRunning?: (running: boolean) => void;
}) {
    const [mode, setMode] = useState<Mode>('observation');
    const [budget, setBudget] = useState('2');
    const [entries, setEntries] = useState<Entry[]>([]);
    const [result, setResult] = useState<RunResult | null>(null);
    const [running, setRunning] = useState(false);
    const active = useRef<AbortController | null>(null);
    const alive = useRef(true);
    useEffect(() => {
        alive.current = true;
        return () => {
            alive.current = false;
            active.current?.abort();
        };
    }, []);
    useEffect(() => {
        const escape = (event: KeyboardEvent) => {
            if (event.key === 'Escape') active.current?.abort();
        };
        window.addEventListener('keydown', escape);
        return () => window.removeEventListener('keydown', escape);
    }, []);

    async function start() {
        if (active.current || !enabled) return;
        const controller = new AbortController();
        active.current = controller;
        setRunning(true);
        onRunning?.(true);
        setResult(null);
        setEntries([]);
        const outcome = await runController(
            adapter,
            mode,
            Number(budget),
            controller.signal,
            (log) => {
                if (alive.current && active.current === controller) setEntries(log);
            },
        );
        if (alive.current && active.current === controller) {
            setResult(outcome);
            setRunning(false);
            onRunning?.(false);
            active.current = null;
        }
    }
    const valid = Number.isInteger(Number(budget)) && Number(budget) >= 1 && Number(budget) <= 5;
    return (
        <section className="panel controller-panel" aria-label="Contrôleur du laboratoire">
            <h3>Observer, décider, vérifier</h3>
            <p className="field-hint">
                Vision locale par couleurs · Scénario fictif à deux clics · Aucun appel au solveur
            </p>
            {native && (
                <p className="field-hint">
                    Ouvre{' '}
                    <a
                        href="http://127.0.0.1:5173/controller-lab.html"
                        target="_blank"
                        rel="noreferrer"
                    >
                        la page de laboratoire
                    </a>
                    , puis le popup SBC Vision sur cet onglet. Seules les pages locales du
                    laboratoire sont acceptées.
                </p>
            )}
            {!enabled && (
                <p className="synthetic-notice">
                    Dans cet aperçu, utilise la page de laboratoire pour tester le contrôleur.
                    L’adaptateur d’onglet nécessite le popup Chrome.
                </p>
            )}
            <label className="field-label">
                Mode du contrôleur
                <select
                    aria-label="Mode du contrôleur"
                    value={mode}
                    disabled={running}
                    onChange={(event) => {
                        setMode(event.target.value as Mode);
                        setResult(null);
                        setEntries([]);
                    }}
                >
                    <option value="observation">Observation</option>
                    <option value="simulation">Simulation sans clic</option>
                    <option value="local">Exécution locale</option>
                </select>
            </label>
            <p className="field-hint">
                {mode === 'local'
                    ? 'Deux clics synthétiques maximum par défaut sur les cartes fictives du laboratoire.'
                    : mode === 'simulation'
                      ? 'Calcule le point du prochain clic et l’état attendu. Ne prédit pas une réussite.'
                      : 'Capture et décrit l’état visible sans exécuter d’action.'}
            </p>
            <label className="field-label controller-budget">
                Budget de clics
                <input
                    aria-label="Budget de clics"
                    type="number"
                    min="1"
                    max="5"
                    value={budget}
                    disabled={running}
                    onChange={(event) => {
                        setBudget(event.target.value);
                        setResult(null);
                        setEntries([]);
                    }}
                />
            </label>
            <div className="controller-buttons">
                <button
                    className="primary-button"
                    onClick={start}
                    disabled={!enabled || running || !valid}
                >
                    {running
                        ? 'Parcours en cours…'
                        : mode === 'local'
                          ? 'Exécuter sur le laboratoire'
                          : mode === 'simulation'
                            ? 'Simuler la prochaine action'
                            : 'Observer le laboratoire'}
                </button>
                <button
                    className="secondary-button"
                    disabled={!running}
                    onClick={() => active.current?.abort()}
                >
                    Interrompre
                </button>
            </div>
            <p className="field-hint">
                Échap interrompt aussi le parcours. Une action déjà envoyée ne peut pas être
                rappelée.
            </p>
            {result && (
                <div
                    className={`controller-outcome ${result.status === 'completed' ? 'success' : ''}`}
                    role="status"
                >
                    <strong>{STATUS[result.status]}</strong>
                    <p>
                        {result.attempts} tentative(s) · {result.clicks} envoi(s) confirmé(s).
                    </p>
                </div>
            )}
            <ol className="controller-log" aria-label="Journal du contrôleur">
                {entries.map((entry, index) => (
                    <li key={index}>
                        <span>{index + 1}</span>
                        <div>
                            {entry.message}
                            {entry.action && (
                                <small>
                                    {entry.action.elementId} → {entry.action.expected} · x{' '}
                                    {entry.action.x.toFixed(1)}, y {entry.action.y.toFixed(1)}
                                </small>
                            )}
                        </div>
                    </li>
                ))}
            </ol>
            <details className="json-details">
                <summary>Voir le journal JSON</summary>
                <pre>{JSON.stringify(result ?? { mode, entries }, null, 2)}</pre>
            </details>
        </section>
    );
}
