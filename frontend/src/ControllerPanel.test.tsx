// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import ControllerPanel from './ControllerPanel';
import type { Frame } from './lib/controller';

function observed(stage = 0): Frame {
    const id = ['lab-select', 'lab-place', 'lab-done'][stage];
    return {
        target: 'local',
        observedAt: Date.now(),
        geometry: {
            width: 640,
            height: 360,
            context: {
                tabId: 1,
                windowId: 1,
                documentId: 'doc',
                viewport: {
                    href: 'http://127.0.0.1:5173/controller-lab.html',
                    width: 640,
                    height: 360,
                    scrollX: 0,
                    scrollY: 0,
                    pixelRatio: 1,
                    visualScale: 1,
                    offsetX: 0,
                    offsetY: 0,
                    timeOrigin: 10,
                    visibility: 'visible',
                },
            },
        },
        perception: {
            schema_version: '0.1',
            capture_id: crypto.randomUUID(),
            model_name: 'local-color-baseline-v1',
            image: { width: 640, height: 360 },
            elements: [
                {
                    id,
                    kind: stage === 2 ? 'text' : 'button',
                    bbox: { x: 30, y: 30, width: 100, height: 40 },
                    confidence: 1,
                    actions: stage === 2 ? [] : ['click'],
                },
            ],
        },
    };
}
function adapter() {
    let stage = 0;
    return {
        observe: vi.fn(async () => observed(stage)),
        click: vi.fn(async () => {
            stage++;
        }),
    };
}
afterEach(cleanup);

it('observe puis simule sans clic et distingue le parcours réellement exécuté', async () => {
    const transport = adapter();
    render(<ControllerPanel adapter={transport} />);
    fireEvent.click(screen.getByRole('button', { name: 'Observer le laboratoire' }));
    await screen.findByText('Observation terminée · Aucun clic');
    expect(transport.click).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('Mode du contrôleur'), {
        target: { value: 'simulation' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Simuler la prochaine action' }));
    await screen.findByText('Simulation terminée · Aucun clic');
    expect(transport.click).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('Mode du contrôleur'), { target: { value: 'local' } });
    fireEvent.click(screen.getByRole('button', { name: 'Exécuter sur le laboratoire' }));
    await screen.findByText('Parcours local vérifié');
    expect(transport.click).toHaveBeenCalledTimes(2);
});
it.each(['button', 'escape'])('interrompt une capture en attente avec %s', async (method) => {
    let complete!: (value: Frame) => void;
    const transport = adapter();
    transport.observe.mockImplementationOnce(
        () =>
            new Promise((resolve) => {
                complete = resolve;
            }),
    );
    render(<ControllerPanel adapter={transport} />);
    fireEvent.click(screen.getByRole('button', { name: 'Observer le laboratoire' }));
    if (method === 'button') fireEvent.click(screen.getByRole('button', { name: 'Interrompre' }));
    else fireEvent.keyDown(window, { key: 'Escape' });
    await screen.findByText('Parcours interrompu');
    await act(async () => complete(observed()));
    expect(transport.click).not.toHaveBeenCalled();
    expect(screen.queryByText('Parcours local vérifié')).toBeNull();
});
it('désactive le transport natif dans un aperçu web', () => {
    const transport = adapter();
    render(<ControllerPanel adapter={transport} enabled={false} native />);
    expect(
        (screen.getByRole('button', { name: 'Observer le laboratoire' }) as HTMLButtonElement)
            .disabled,
    ).toBe(true);
    expect(transport.observe).not.toHaveBeenCalled();
});

it('attend la connexion API avant de commencer les captures et affiche un refus sans cliquer', async () => {
    const transport = adapter();
    const beforeStart = vi.fn(async () => false);
    render(<ControllerPanel adapter={transport} beforeStart={beforeStart} />);
    fireEvent.click(screen.getByRole('button', { name: 'Observer le laboratoire' }));
    await screen.findByText('Vérification impossible · Contrôleur arrêté');
    expect(beforeStart).toHaveBeenCalledOnce();
    expect(transport.observe).not.toHaveBeenCalled();
    expect(transport.click).not.toHaveBeenCalled();
});

it('ignore une connexion confirmée après l’interruption du parcours', async () => {
    const transport = adapter();
    let connected!: (value: boolean) => void;
    const beforeStart = () =>
        new Promise<boolean>((resolve) => {
            connected = resolve;
        });
    render(<ControllerPanel adapter={transport} beforeStart={beforeStart} />);
    fireEvent.click(screen.getByRole('button', { name: 'Observer le laboratoire' }));
    fireEvent.click(screen.getByRole('button', { name: 'Interrompre' }));
    await screen.findByText('Parcours interrompu');
    await act(async () => connected(true));
    await screen.findByText('Parcours interrompu');
    expect(transport.observe).not.toHaveBeenCalled();
});
