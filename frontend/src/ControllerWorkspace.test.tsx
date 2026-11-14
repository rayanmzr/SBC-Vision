// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import ControllerWorkspace from './ControllerWorkspace';
import type { LabPerceiver } from './lib/lab-api';
import type { ControllerAdapter } from './lib/controller';
import { DEFAULT_API_URL } from './lib/platform';

afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
});
it('ne contacte pas l’API lors du choix de source et arrête le parcours sur son erreur réelle', async () => {
    const fetchMock = vi.fn(
        async () =>
            new Response(
                JSON.stringify({
                    detail: { code: 'perception_unavailable', message: 'Pipeline absent.' },
                }),
                { status: 503 },
            ),
    );
    vi.stubGlobal('fetch', fetchMock);
    const clicks = vi.fn(async () => {});
    const makeAdapter = (perceive?: LabPerceiver): ControllerAdapter => ({
        observe: async (signal) => {
            if (perceive)
                await perceive(
                    new Blob(['pixels'], { type: 'image/png' }),
                    { width: 640, height: 270 },
                    signal,
                );
            throw new Error('Le transport navigateur ne doit pas être substitué.');
        },
        click: clicks,
    });
    render(<ControllerWorkspace makeAdapter={makeAdapter} apiUrl={DEFAULT_API_URL} />);
    fireEvent.change(screen.getByLabelText('Analyse des images'), { target: { value: 'api' } });
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Observer le laboratoire' }));
    await screen.findByText('Pipeline absent.');
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(clicks).not.toHaveBeenCalled();
    expect(screen.getByText('Vérification impossible · Contrôleur arrêté')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Analyse des images'), { target: { value: 'browser' } });
    expect(screen.queryByText('Pipeline absent.')).toBeNull();
    expect(fetchMock).toHaveBeenCalledOnce();
});
