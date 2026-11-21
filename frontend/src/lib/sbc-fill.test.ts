// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { fillSbc, placementInTab, type PreparedSbc } from './sbc-fill';
import { activeContext, type TabContext } from './tab-capture';
import { loadWorkspace, type PlacementCard } from './sbc-api';
import fixture from '../../../data/fixtures/workspace-api.synthetic.json';

vi.mock('./tab-capture', () => ({ activeContext: vi.fn() }));
vi.mock('./sbc-api', () => ({ loadWorkspace: vi.fn() }));
const card: PlacementCard = {
    slot: 0,
    candidate_key: 'club:synthetic',
    card_id: 900001,
    reading: {
        name: 'Exemple fictif',
        rating: 83,
        position: 'CM',
        nation_id: 1,
        league_id: 2,
        club_id: 3,
        stats: { PAC: 70, SHO: 60, PAS: 80, DRI: 75, DEF: 50, PHY: 65 },
    },
};
const context = {
    tabId: 1,
    documentId: 'synthetic-document',
    viewport: { href: 'https://www.ea.com/ea-sports-fc/ultimate-team/web-app/' },
} as TabContext;
const logos =
    '<img src="https://example.test/flags/1.png"><img src="https://example.test/leagues/2.png"><img src="https://example.test/clubs/3.png">';
let submitted: ReturnType<typeof vi.fn<() => void>>, added: ReturnType<typeof vi.fn<() => void>>;
function row(name = card.reading.name) {
    return `<li class="listFUTItem"><button class="btnAction add">+</button><div class="entityContainer"><div class="player item"><div class="playerOverview"><span class="rating">83</span><span class="position">CM</span></div></div><div class="name">${name}</div>${logos}<div class="player-stats-data-component"><ul>${Object.entries(
        card.reading.stats,
    )
        .map(([k, v]) => `<li><span class="label">${k}</span><span class="value">${v}</span></li>`)
        .join('')}</ul></div></div></li>`;
}
function results(firstPage = false) {
    document.querySelector('#panel')!.innerHTML =
        `<div class="ut-club-search-results-view sbc"><div class="paginated-item-list"><ul>${row(firstPage ? 'Autre joueur fictif' : undefined)}</ul></div>${firstPage ? '<button class="pagination next">Next</button>' : ''}</div>`;
    document.querySelector('.next')?.addEventListener('mouseup', () => results());
    document.querySelector('.add')!.addEventListener('mouseup', () => {
        added();
        document.querySelector('.ut-squad-slot-view .player.item')!.outerHTML =
            `<div class="player item"><div class="playerOverview"><span class="rating">83</span></div>${logos}</div>`;
    });
}
function proposal(): PreparedSbc {
    return {
        ...fixture.proposal,
        mode: 'local',
        context,
        revision: 'a'.repeat(64),
        board: placementInTab().board,
        report: {
            ...fixture.proposal.report,
            data_kind: 'local',
            challenge: { ...fixture.proposal.report.challenge, positions: ['CM'] },
            solution: {
                status: 'optimal',
                assignments: [{ slot: 0, candidate_key: card.candidate_key }],
            },
            selected_candidates: [
                {
                    ...fixture.proposal.report.selected_candidates[0],
                    key: card.candidate_key,
                    card_id: card.card_id,
                    owned: true,
                    protected: false,
                },
            ],
            verification: { valid: true, checks: [] },
        },
        placement: { cards: [structuredClone(card)], issues: [] },
    } as PreparedSbc;
}
beforeEach(() => {
    vi.stubGlobal('location', {
        protocol: 'https:',
        hostname: 'www.ea.com',
        pathname: '/ea-sports-fc/ultimate-team/web-app/',
    });
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue(
        new DOMRect(0, 0, 100, 100),
    );
    document.body.innerHTML = `<h1 class="title">SBC fictif</h1><ul class="sbc-requirements-checklist"><li>Number of Players: 1</li></ul><div class="ut-squad-slot-view" index="0"><div class="ut-squad-slot-pedestal-view"><span class="label">CM</span></div><div class="player item empty"></div></div><div id="panel"></div><button id="submit">Submit</button><button id="exchange">Exchange Players</button>`;
    submitted = vi.fn();
    added = vi.fn();
    document
        .querySelectorAll('#submit,#exchange')
        .forEach((e) => e.addEventListener('mouseup', submitted));
    document.querySelector('.ut-squad-slot-view')!.addEventListener('mouseup', (e) => {
        if (e.target !== e.currentTarget) return;
        document.querySelector('.ut-squad-slot-view')!.classList.add('ui-slot-selected');
        document.querySelector('#panel')!.innerHTML = '<button>Add Player</button>';
        document.querySelector('#panel button')!.addEventListener('mouseup', () => {
            document.querySelector('#panel')!.innerHTML =
                '<div class="ut-club-search-filters-view sbc"><button>Search</button></div>';
            document
                .querySelector('#panel button')!
                .addEventListener('mouseup', () => results(true));
        });
    });
    vi.mocked(activeContext).mockReset().mockResolvedValue(context);
    vi.mocked(loadWorkspace)
        .mockReset()
        .mockResolvedValue({
            ...fixture.workspace,
            mode: 'local',
            revision: 'a'.repeat(64),
        } as Awaited<ReturnType<typeof loadWorkspace>>);
    vi.stubGlobal('chrome', {
        scripting: {
            executeScript: vi.fn(async (o: { args: Parameters<typeof placementInTab> }) => [
                { frameId: 0, documentId: context.documentId, result: placementInTab(...o.args) },
            ]),
        },
    });
});
afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    document.body.innerHTML = '';
});

it('observe sans agir puis teste tout le parcours fictif jusqu’au placement, sans soumission', async () => {
    expect(placementInTab().slots[0].card).toBeNull();
    expect(added).not.toHaveBeenCalled();
    const p = proposal();
    p.board = {
        positions: p.board.positions,
        slot_indices: p.board.slot_indices,
        requirements: p.board.requirements,
        title: p.board.title,
    };
    await expect(
        fillSbc('http://localhost', p, new AbortController().signal, vi.fn()),
    ).resolves.toBe(1);
    expect(added).toHaveBeenCalledOnce();
    expect(submitted).not.toHaveBeenCalled();
    expect(loadWorkspace).toHaveBeenCalledTimes(2);
});

it('remplit l’unique case ouverte même si son indice EA est 10, sans cliquer les cadenas', async () => {
    document.querySelector('.ut-squad-slot-view')!.setAttribute('index', '10');
    document.body.insertAdjacentHTML(
        'beforeend',
        Array.from(
            { length: 10 },
            (_, i) =>
                `<div class="ut-squad-slot-view locked" index="${i}"><div class="ut-squad-slot-pedestal-view"><span class="label">CM</span></div><div class="player item empty"></div></div>`,
        ).join(''),
    );
    const locked = vi.fn();
    document.querySelectorAll('.locked').forEach((e) => e.addEventListener('mouseup', locked));
    const p = proposal();
    expect(p.board.slot_indices).toEqual([10]);
    await expect(
        fillSbc('http://localhost', p, new AbortController().signal, vi.fn()),
    ).resolves.toBe(1);
    expect(document.querySelector('[index="10"] .player.item.empty')).toBeNull();
    expect(locked).not.toHaveBeenCalled();
    expect(submitted).not.toHaveBeenCalled();
});

it('retire le filtre de poste avant une recherche libre sans cliquer sur le marché', async () => {
    document.querySelector('.ut-squad-slot-view')!.classList.add('ui-slot-selected');
    document.querySelector('#panel')!.innerHTML =
        '<div class="ut-club-search-filters-view sbc"><div class="ut-search-filter-control"><img src="https://example.test/positions/0.png"><span class="label">GK</span><button class="ut-search-filter-control--row-button">×</button></div><button id="search">Search</button></div>';
    document.querySelector('.ut-search-filter-control button')!.addEventListener('mouseup', () => {
        document.querySelector('.ut-search-filter-control .label')!.textContent = 'Position';
    });
    const search = vi.fn();
    document.querySelector('#search')!.addEventListener('mouseup', search);
    const p = proposal();
    p.report.challenge.position_mode = 'any';
    let state = placementInTab();
    placementInTab({ action: 'clear-position', signature: state.signature, card });
    state = placementInTab();
    expect(state.position_filter).toBe('Position');
    expect(search).not.toHaveBeenCalled();
    expect(submitted).not.toHaveBeenCalled();
});

it.each(['duplicate', 'stats', 'loan', 'active', 'stale', 'occupied', 'wrong-slot'])(
    'refuse de cliquer si la carte ou la scène est incertaine : %s',
    (fault) => {
        results();
        document.querySelector('.ut-squad-slot-view')!.classList.add('ui-slot-selected');
        const old = placementInTab().signature;
        if (fault === 'duplicate')
            document
                .querySelector('.paginated-item-list ul')!
                .insertAdjacentHTML('beforeend', row());
        if (fault === 'stats') document.querySelector('.value')!.textContent = '99';
        if (fault === 'loan') document.querySelector('.listFUTItem .player')!.classList.add('loan');
        if (fault === 'active') document.querySelector('.listFUTItem')!.classList.add('is-active');
        if (fault === 'occupied') document.querySelector('.empty')!.classList.remove('empty');
        if (fault === 'wrong-slot')
            document.querySelector('.ui-slot-selected')!.classList.remove('ui-slot-selected');
        const signature = fault === 'stale' ? old + '-old' : placementInTab().signature;
        expect(() => placementInTab({ action: 'place', card, signature })).toThrow();
        expect(added).not.toHaveBeenCalled();
        expect(submitted).not.toHaveBeenCalled();
    },
);

it.each(['purchase', 'revision', 'challenge', 'layout', 'abort'])(
    'arrête le contrôleur avant toute action : %s',
    async (fault) => {
        const p = proposal(),
            controller = new AbortController();
        if (fault === 'purchase') p.placement = { cards: [], issues: ['À acheter manuellement.'] };
        if (fault === 'revision')
            vi.mocked(loadWorkspace).mockResolvedValue({
                ...fixture.workspace,
                mode: 'local',
                revision: 'b'.repeat(64),
            } as Awaited<ReturnType<typeof loadWorkspace>>);
        if (fault === 'challenge') p.board.title = 'Autre SBC';
        if (fault === 'layout') p.board.slot_indices = [10];
        if (fault === 'abort') controller.abort();
        await expect(fillSbc('http://localhost', p, controller.signal, vi.fn())).rejects.toThrow();
        expect(added).not.toHaveBeenCalled();
        expect(submitted).not.toHaveBeenCalled();
    },
);

it('relit les protections après la recherche et refuse de placer une carte devenue protégée', async () => {
    const current = { ...fixture.workspace, mode: 'local', revision: 'a'.repeat(64) } as Awaited<
        ReturnType<typeof loadWorkspace>
    >;
    vi.mocked(loadWorkspace)
        .mockResolvedValueOnce(current)
        .mockResolvedValueOnce({ ...current, revision: 'b'.repeat(64) });
    await expect(
        fillSbc('http://localhost', proposal(), new AbortController().signal, vi.fn()),
    ).rejects.toThrow('Inventaire modifié');
    expect(added).not.toHaveBeenCalled();
    expect(placementInTab().slots[0].card).toBeNull();
    expect(submitted).not.toHaveBeenCalled();
});

it('signale un placement déjà effectué si la composition diverge ensuite', async () => {
    const p = proposal();
    added.mockImplementation(() => {
        document.querySelector('h1')!.textContent = 'Autre SBC';
    });
    await expect(
        fillSbc('http://localhost', p, new AbortController().signal, vi.fn()),
    ).rejects.toThrow('Arrêt après 1 placement(s)');
    expect(added).toHaveBeenCalledOnce();
    expect(submitted).not.toHaveBeenCalled();
});
