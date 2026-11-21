import { validatePerception, type Perception } from './api';
import { imagePointToViewport, type TabCapture } from './tab-capture';

export type Geometry = Pick<TabCapture, 'width' | 'height' | 'context'>;
export type Frame = {
    geometry: Geometry;
    perception: Perception;
    target: string;
    observedAt: number;
};
export type Action = { type: 'click'; elementId: string; x: number; y: number; expected: string };
export type ControllerAdapter = {
    observe: (signal: AbortSignal) => Promise<Frame>;
    click: (frame: Frame, action: Action, signal: AbortSignal) => Promise<void>;
};
export type Mode = 'observation' | 'simulation' | 'local';
export type Entry = { kind: string; message: string; action?: Action; perception?: Perception };
export type RunResult = {
    mode: Mode;
    status:
        'observed' | 'simulated' | 'completed' | 'step_limit' | 'diverged' | 'cancelled' | 'failed';
    clicks: number;
    attempts: number;
    entries: Entry[];
};
const NEXT: Record<string, string> = { 'lab-select': 'lab-place', 'lab-place': 'lab-done' };

export function planLocalAction(frame: Frame, now = Date.now()): Action | null {
    const data = validatePerception(frame.perception, {
        captureId: frame.perception.capture_id,
        width: frame.geometry.width,
        height: frame.geometry.height,
    });
    if (
        !Number.isFinite(frame.observedAt) ||
        now - frame.observedAt > 5000 ||
        frame.observedAt > now + 100
    )
        throw new Error('Observation périmée.');
    if (
        !['local-color-baseline-v1', 'lab-color-api-v1'].includes(data.model_name) ||
        data.elements.length !== 1
    )
        throw new Error('État local absent ou ambigu.');
    const element = data.elements[0];
    if (element.confidence < 0.95) throw new Error('Confiance insuffisante.');
    // Même une fin de parcours doit posséder un repère de coordonnées valide.
    const point = imagePointToViewport(frame.geometry, element.bbox);
    if (element.id === 'lab-done' && element.kind === 'text' && !element.actions?.length)
        return null;
    if (
        !NEXT[element.id] ||
        element.kind !== 'button' ||
        element.actions?.length !== 1 ||
        element.actions[0] !== 'click'
    )
        throw new Error('Action non autorisée par le scénario local.');
    return { type: 'click', elementId: element.id, ...point, expected: NEXT[element.id] };
}

function sameFrame(a: Frame, b: Frame) {
    return (
        a.target === b.target &&
        JSON.stringify(a.geometry) === JSON.stringify(b.geometry) &&
        JSON.stringify(a.perception.elements) === JSON.stringify(b.perception.elements)
    );
}

// Un adaptateur doit respecter le signal avant tout effet ; les clics sont immédiats,
// sans tentative automatique supplémentaire après erreur.
async function bounded<T>(
    work: (signal: AbortSignal) => Promise<T>,
    parent: AbortSignal,
): Promise<T> {
    parent.throwIfAborted();
    const deadline = new AbortController();
    const signal = AbortSignal.any([parent, deadline.signal]);
    let rejectAbort!: () => void;
    const aborted = new Promise<never>((_, reject) => {
        rejectAbort = () =>
            reject(
                parent.aborted
                    ? new Error('Interrompu.')
                    : new Error('Délai de l’opération dépassé.'),
            );
        signal.addEventListener('abort', rejectAbort, { once: true });
    });
    const timer = setTimeout(() => deadline.abort(), 8000);
    try {
        return await Promise.race([work(signal), aborted]);
    } finally {
        clearTimeout(timer);
        signal.removeEventListener('abort', rejectAbort);
    }
}

export async function runController(
    adapter: ControllerAdapter,
    mode: Mode,
    maxSteps: number,
    signal: AbortSignal,
    notify: (entries: Entry[]) => void = () => {},
): Promise<RunResult> {
    const entries: Entry[] = [];
    let clicks = 0;
    let attempts = 0;
    const captures = new Set<string>();
    async function observe() {
        const observed = await bounded(adapter.observe, signal);
        signal.throwIfAborted();
        if (captures.has(observed.perception.capture_id))
            throw new Error('Ancienne capture réutilisée.');
        captures.add(observed.perception.capture_id);
        return observed;
    }
    const emit = (entry: Entry) => {
        entries.push(entry);
        notify([...entries]);
    };
    const finish = (status: RunResult['status']) => ({ mode, status, attempts, clicks, entries });
    try {
        if (
            !['observation', 'simulation', 'local'].includes(mode) ||
            !Number.isInteger(maxSteps) ||
            maxSteps < 1 ||
            maxSteps > 5
        )
            throw new Error('Budget attendu : un à cinq clics.');
        let frame = await observe();
        signal.throwIfAborted();
        emit({
            kind: 'capture',
            message: 'Image analysée ; JSON de perception obtenu.',
            perception: frame.perception,
        });
        while (true) {
            signal.throwIfAborted();
            const action = planLocalAction(frame);
            if (!action) {
                emit({ kind: 'verified', message: 'État final reconnu dans la nouvelle image.' });
                return finish(
                    mode === 'local'
                        ? 'completed'
                        : mode === 'simulation'
                          ? 'simulated'
                          : 'observed',
                );
            }
            if (mode !== 'local') {
                emit({
                    kind: 'plan',
                    action,
                    message:
                        mode === 'simulation'
                            ? 'Clic préparé uniquement ; aucun événement envoyé, résultat non vérifié.'
                            : 'État observé ; aucune action exécutée.',
                });
                return finish(mode === 'simulation' ? 'simulated' : 'observed');
            }
            if (attempts >= maxSteps) {
                emit({ kind: 'limit', message: 'Budget de clics atteint. Parcours incomplet.' });
                return finish('step_limit');
            }
            const fresh = await observe();
            signal.throwIfAborted();
            planLocalAction(fresh);
            if (!sameFrame(frame, fresh)) {
                emit({ kind: 'divergence', message: 'La cible a changé avant le clic. Arrêt.' });
                return finish('diverged');
            }
            attempts++;
            emit({
                kind: 'attempt',
                action,
                message: 'Tentative de clic local ; confirmation attendue.',
            });
            await bounded((nextSignal) => adapter.click(fresh, action, nextSignal), signal);
            signal.throwIfAborted();
            clicks++;
            emit({
                kind: 'click',
                action,
                message: `Clic local envoyé à (${action.x.toFixed(1)}, ${action.y.toFixed(1)}).`,
            });
            const next = await observe();
            signal.throwIfAborted();
            planLocalAction(next);
            emit({
                kind: 'capture',
                message: 'Nouvelle image après le clic.',
                perception: next.perception,
            });
            if (
                next.target !== frame.target ||
                JSON.stringify(next.geometry) !== JSON.stringify(frame.geometry) ||
                next.perception.elements[0].id !== action.expected
            ) {
                emit({
                    kind: 'divergence',
                    message: 'L’écran attendu n’est pas apparu. Arrêt sans nouveau clic.',
                });
                return finish('diverged');
            }
            emit({
                kind: 'verified',
                message: `Transition vérifiée : ${action.elementId} → ${action.expected}.`,
            });
            frame = next;
        }
    } catch (error) {
        emit({
            kind: signal.aborted ? 'cancel' : 'error',
            message: signal.aborted
                ? 'Interruption utilisateur. Une action déjà envoyée ne peut pas être rappelée.'
                : error instanceof Error
                  ? error.message
                  : 'Opération refusée.',
        });
        return finish(signal.aborted ? 'cancelled' : 'failed');
    }
}
