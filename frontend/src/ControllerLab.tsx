import { useCallback, useLayoutEffect, useMemo, useRef, useState } from 'react';
import ControllerWorkspace from './ControllerWorkspace';
import type { LabPerceiver } from './lib/lab-api';
import { canvasLabAdapter } from './lib/lab-adapter';
import { LAB_COLORS } from './lib/lab-vision';

const MARKERS = [
    { x: 48, y: 174 },
    { x: 360, y: 174 },
    { x: 204, y: 174 },
];

export default function ControllerLab() {
    const canvas = useRef<HTMLCanvasElement>(null);
    const [node, setNode] = useState<HTMLCanvasElement | null>(null);
    const [stage, setStage] = useState(0);
    const [fault, setFault] = useState('none');
    const [running, setRunning] = useState(false);
    const [generation, setGeneration] = useState(0);
    const bindCanvas = useCallback((value: HTMLCanvasElement | null) => {
        canvas.current = value;
        setNode(value);
    }, []);
    const makeAdapter = useMemo(
        () => (node ? (perceive?: LabPerceiver) => canvasLabAdapter(node, perceive) : null),
        [node],
    );
    useLayoutEffect(() => {
        const context = canvas.current?.getContext('2d');
        if (!context) return;
        context.fillStyle = '#f0f4ef';
        context.fillRect(0, 0, 640, 270);
        context.fillStyle = '#23483d';
        context.font = 'bold 23px sans-serif';
        context.fillText(
            ['Club fictif', 'Carte sélectionnée', 'Carte fictive placée'][stage],
            32,
            44,
        );
        context.font = '15px sans-serif';
        context.fillText(
            [
                '1. Sélectionner Alex Exemple',
                '2. Placer la carte dans le slot',
                'État final à vérifier dans les pixels',
            ][stage],
            32,
            77,
        );
        context.fillStyle = '#dfe5d6';
        context.fillRect(32, 98, 576, 46);
        context.fillStyle = '#435849';
        context.font = '16px sans-serif';
        context.fillText('83  ·  Alex Exemple  ·  CM', 48, 127);
        const marker = LAB_COLORS[stage];
        context.fillStyle = `rgb(${marker.rgb.join(',')})`;
        context.fillRect(MARKERS[stage].x, MARKERS[stage].y, 232, 58);
        context.fillStyle = '#435849';
        context.font = '12px sans-serif';
        context.fillText('Le rectangle plein est le repère visuel de l’action.', 32, 254);
    }, [stage]);
    return (
        <main className="app-shell lab-shell">
            <header className="lab-header">
                <p className="eyebrow">SBC VISION · LABORATOIRE DU CONTRÔLEUR</p>
                <h1>Une action, puis une preuve visuelle.</h1>
                <p>
                    Deux transitions sur une carte fictive. Les couleurs sont reconnues dans l’image
                    ; aucun détecteur de joueurs n’est évalué ici.
                </p>
            </header>
            <div className="lab-grid">
                <section className="panel lab-scene" aria-label="Page locale à observer">
                    <div className="report-section-heading">
                        <h2>Zone de test</h2>
                        <span className="kind-label">DONNÉES FICTIVES</span>
                    </div>
                    <canvas
                        width="640"
                        height="270"
                        data-sbc-controller-lab="v1"
                        aria-label="Scène visuelle du laboratoire"
                        ref={bindCanvas}
                        onClick={(event) => {
                            if (stage >= 2) return;
                            const rect = event.currentTarget.getBoundingClientRect();
                            const x = ((event.clientX - rect.left) * 640) / rect.width;
                            const y = ((event.clientY - rect.top) * 270) / rect.height;
                            const point = MARKERS[stage];
                            if (
                                x < point.x ||
                                x >= point.x + 232 ||
                                y < point.y ||
                                y >= point.y + 58 ||
                                fault === 'no-change'
                            )
                                return;
                            setStage(fault === 'unexpected' ? 2 : stage + 1);
                        }}
                    />
                    <p className="lab-state" role="status">
                        État de la page :{' '}
                        {['carte disponible', 'carte sélectionnée', 'carte placée'][stage]}
                    </p>
                    <p className="field-hint">
                        Ce statut explique le test. Le contrôleur déduit l’état depuis les pixels du
                        canevas, puis vérifie une nouvelle image.
                    </p>
                    <p className="field-hint">
                        Pour exécuter les clics, garde la scène et les commandes visibles ensemble.
                        Agrandis la fenêtre si nécessaire.
                    </p>
                    <label className="field-label">
                        Comportement de la page
                        <select
                            aria-label="Comportement de la page"
                            disabled={running}
                            value={fault}
                            onChange={(event) => {
                                setFault(event.target.value);
                                setStage(0);
                                setGeneration((previous) => previous + 1);
                            }}
                        >
                            <option value="none">Parcours normal</option>
                            <option value="no-change">Le clic ne change rien</option>
                            <option value="unexpected">L’écran suivant est inattendu</option>
                        </select>
                    </label>
                    <button
                        className="secondary-button"
                        disabled={running}
                        onClick={() => {
                            setStage(0);
                            setGeneration((previous) => previous + 1);
                        }}
                    >
                        Réinitialiser la page
                    </button>
                    <p className="field-hint">
                        Dans le navigateur, l’image provient du canevas exporté en PNG. Dans le
                        popup Chrome, elle provient de la capture de l’onglet entier. Le clic de
                        test est un événement synthétique réservé à cette page.
                    </p>
                    <a className="lab-return" href="/">
                        Retour à SBC Vision
                    </a>
                </section>
                {makeAdapter && (
                    <ControllerWorkspace
                        key={generation}
                        makeAdapter={makeAdapter}
                        onRunning={setRunning}
                    />
                )}
            </div>
        </main>
    );
}
