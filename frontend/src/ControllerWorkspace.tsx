import { useCallback, useMemo, useState } from 'react';
import ControllerPanel from './ControllerPanel';
import { apiLabPerceiver, type LabPerceiver } from './lib/lab-api';
import type { ControllerAdapter } from './lib/controller';
import { DEFAULT_API_URL, normalizeApiUrl } from './lib/platform';

export default function ControllerWorkspace({
    makeAdapter,
    native = false,
    enabled = true,
    apiUrl = DEFAULT_API_URL,
    beforeApiStart,
    onRunning,
}: {
    makeAdapter: (perceive?: LabPerceiver) => ControllerAdapter;
    native?: boolean;
    enabled?: boolean;
    apiUrl?: string;
    beforeApiStart?: () => Promise<boolean>;
    onRunning?: (running: boolean) => void;
}) {
    const [source, setSource] = useState<'browser' | 'api'>('browser');
    const [running, setRunning] = useState(false);
    const base = useMemo(() => {
        try {
            return normalizeApiUrl(apiUrl);
        } catch {
            return apiUrl;
        }
    }, [apiUrl]);
    const adapter = useMemo(
        () => makeAdapter(source === 'api' ? apiLabPerceiver(base) : undefined),
        [makeAdapter, source, base],
    );
    const runningChanged = useCallback(
        (value: boolean) => {
            setRunning(value);
            onRunning?.(value);
        },
        [onRunning],
    );
    return (
        <div className="controller-workspace">
            <div className="panel controller-source">
                <label className="field-label">
                    Analyse des images
                    <select
                        aria-label="Analyse des images"
                        value={source}
                        disabled={running}
                        onChange={(event) => setSource(event.target.value as 'browser' | 'api')}
                    >
                        <option value="browser">Dans le navigateur · Couleurs de test</option>
                        <option value="api">API Python · Couleurs de test</option>
                    </select>
                </label>
                <p className="field-hint">
                    {source === 'api'
                        ? `Serveur : ${base}. Le lancement envoie chaque nouvelle image à cette API, puis utilise uniquement son JSON. Aucun retour automatique au traitement navigateur.`
                        : 'Les images restent dans le navigateur. Ce mode ne contacte pas l’API.'}
                </p>
            </div>
            <ControllerPanel
                key={`${source}:${base}`}
                adapter={adapter}
                native={native}
                enabled={enabled}
                beforeStart={source === 'api' ? beforeApiStart : undefined}
                onRunning={runningChanged}
                perceptionLabel={
                    source === 'api'
                        ? 'Vision via l’API Python · Couleurs de test'
                        : 'Vision locale par couleurs'
                }
            />
        </div>
    );
}
