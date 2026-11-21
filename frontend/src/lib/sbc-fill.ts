import { activeContext, type TabContext } from './tab-capture';
import { loadWorkspace, type ApiProposal, type PlacementCard } from './sbc-api';

type Command = {
    action: 'open' | 'club' | 'clear-position' | 'search' | 'next' | 'place';
    signature: string;
    card: PlacementCard;
};
export type PreparedSbc = ApiProposal & {
    context: TabContext;
    board: { title: string; requirements: string; positions: string[]; slot_indices: number[] };
};

// Fonction autonome injectée dans EA. La liste des actions ne contient aucun échange.
export function placementInTab(command?: Command) {
    if (
        location.protocol !== 'https:' ||
        !['ea.com', 'www.ea.com'].includes(location.hostname) ||
        !location.pathname.includes('/ultimate-team/web-app/')
    )
        throw new Error('Ouvrir la Web App EA.');
    const text = (root: ParentNode, selector: string) =>
        root.querySelector(selector)?.textContent?.trim() ?? '';
    const logo = (root: ParentNode, kind: string) => {
        const image = Array.from(root.querySelectorAll('img')).find((i) =>
            i.src.includes(`/${kind}/`),
        );
        return Number(image?.src.match(/\/(\d+)\.png(?:\?.*)?$/)?.[1]) || null;
    };
    const available = (e: Element | null) =>
        !!e &&
        !e.hasAttribute('disabled') &&
        e.getAttribute('aria-disabled') !== 'true' &&
        !e.classList.contains('disabled') &&
        getComputedStyle(e).display !== 'none' &&
        getComputedStyle(e).visibility !== 'hidden' &&
        e.getBoundingClientRect().width > 0;
    const roots = Array.from(document.querySelectorAll<HTMLElement>('.ut-squad-slot-view')).filter(
        (e) =>
            !e.classList.contains('locked') &&
            e.getBoundingClientRect().width > 0 &&
            /^(?:\d|10)$/.test(e.getAttribute('index') ?? '') &&
            /^[A-Z]{2,3}$/.test(text(e, '.ut-squad-slot-pedestal-view .label')),
    );
    const slots = roots.map((e, index) => ({
        index,
        ea_index: Number(e.getAttribute('index')),
        position: text(e, '.ut-squad-slot-pedestal-view .label'),
        card: e.querySelector('.player.item.empty')
            ? null
            : {
                  rating: Number(text(e, '.playerOverview .rating')),
                  nation_id: logo(e, 'flags'),
                  league_id: logo(e, 'leagues'),
                  club_id: logo(e, 'clubs'),
              },
    }));
    const checklist = Array.from(document.querySelectorAll('.sbc-requirements-checklist')).find(
        (e) => e.children.length,
    );
    const board = {
        title: text(document, 'h1.title'),
        requirements: checklist
            ? Array.from(checklist.children)
                  .map((e) => e.textContent?.trim())
                  .join('\n')
            : '',
        positions: slots.map((s) => s.position),
        slot_indices: slots.map((s) => s.ea_index),
    };
    if (
        !board.title ||
        !board.requirements ||
        !slots.length ||
        slots.length > 11 ||
        slots.some((s) => !Number.isInteger(s.ea_index) || s.ea_index < 0 || s.ea_index > 10) ||
        new Set(board.slot_indices).size !== slots.length
    )
        throw new Error('Composition ou conditions illisibles ; aucun placement.');
    const panel = document.querySelector('.ut-club-search-results-view.sbc');
    const elements = Array.from(
        panel?.querySelectorAll('.paginated-item-list li.listFUTItem') ?? [],
    );
    const rows = elements.map((e) => ({
        name: text(e, '.entityContainer > .name'),
        rating: Number(text(e, '.playerOverview .rating')),
        position: text(e, '.playerOverview .position'),
        stats: Object.fromEntries(
            Array.from(e.querySelectorAll('.player-stats-data-component li')).map((s) => [
                text(s, '.label'),
                /^\d{1,2}$/.test(text(s, '.value')) ? Number(text(s, '.value')) : NaN,
            ]),
        ),
        nation_id: logo(e, 'flags'),
        league_id: logo(e, 'leagues'),
        club_id: logo(e, 'clubs'),
        loan: !!e.querySelector('.player.item.loan'),
        active: e.classList.contains('is-active') || !!e.querySelector('.ut-list-active-tag-view'),
        add: available(e.querySelector('button.btnAction.add')),
    }));
    const filters = document.querySelector('.ut-club-search-filters-view.sbc');
    const positionFilter = Array.from(
        filters?.querySelectorAll('.ut-search-filter-control') ?? [],
    ).find(
        (e) =>
            e.querySelector('img')?.src.includes('/positions/') || text(e, '.label') === 'Position',
    );
    const addButtons = Array.from(document.querySelectorAll('button')).filter(
        (b) => b.textContent?.trim() === 'Add Player' && available(b),
    );
    const stage = panel
        ? 'results'
        : filters
          ? 'filters'
          : addButtons.length === 1
            ? 'details'
            : 'squad';
    const selected = roots.findIndex((e) => e.classList.contains('ui-slot-selected'));
    const next = panel?.querySelector('button.pagination.next') ?? null;
    const state = {
        board,
        slots,
        rows,
        stage,
        selected,
        hasNext: available(next),
        position_filter: positionFilter ? text(positionFilter, '.label') : null,
    };
    const signature = JSON.stringify(state);
    if (!command) return { ...state, signature };
    if (command.signature !== signature) throw new Error('L’écran a changé ; arrêt du placement.');
    const { card, action } = command;
    if (!Number.isInteger(card.slot) || !slots[card.slot] || slots[card.slot].card)
        throw new Error('Case occupée ou absente ; aucun remplacement.');
    let button: Element | null = null;
    if (action === 'open') button = roots[card.slot];
    else {
        if (selected !== card.slot) throw new Error('La case sélectionnée a changé.');
        if (action === 'club' && stage === 'details') button = addButtons[0];
        if (
            action === 'clear-position' &&
            stage === 'filters' &&
            state.position_filter !== 'Position'
        )
            button =
                positionFilter?.querySelector('button.ut-search-filter-control--row-button') ??
                null;
        if (action === 'search' && stage === 'filters')
            button =
                Array.from(filters!.querySelectorAll('button')).find(
                    (b) => b.textContent?.trim() === 'Search',
                ) ?? null;
        if (action === 'next' && stage === 'results' && state.hasNext) button = next;
        if (action === 'place' && stage === 'results') {
            const expected = card.reading;
            const matches = rows
                .map((r, i) => ({ r, i }))
                .filter(
                    ({ r }) =>
                        !r.loan &&
                        r.name === expected.name &&
                        r.rating === expected.rating &&
                        r.position === expected.position &&
                        ['nation_id', 'league_id', 'club_id'].every(
                            (k) => r[k as 'nation_id'] === expected[k as 'nation_id'],
                        ) &&
                        Object.keys(r.stats).length === 6 &&
                        Object.keys(expected.stats).length === 6 &&
                        Object.entries(expected.stats).every(([k, n]) => r.stats[k] === n),
                );
            if (matches.length !== 1 || matches[0].r.active || !matches[0].r.add)
                throw new Error('Version ambiguë, prêt ou carte indisponible ; arrêt.');
            button = elements[matches[0].i].querySelector('button.btnAction.add');
        }
    }
    if (!available(button)) throw new Error('Action attendue absente ; arrêt.');
    // Un seul bouton autorisé par étape. Ni Submit, ni Exchange, ni marché des transferts.
    const box = button!.getBoundingClientRect();
    for (const type of ['mousedown', 'mouseup', 'click'])
        button!.dispatchEvent(
            new MouseEvent(type, {
                bubbles: true,
                button: 0,
                buttons: type === 'mousedown' ? 1 : 0,
                clientX: box.x + box.width / 2,
                clientY: box.y + box.height / 2,
            }),
        );
    return { ...state, signature };
}

export async function fillSbc(
    base: string,
    proposal: PreparedSbc,
    signal: AbortSignal,
    progress: (s: string) => void,
) {
    signal.throwIfAborted();
    const { report, placement } = proposal;
    if (
        proposal.mode !== 'local' ||
        report.data_kind !== 'local' ||
        !report.verification?.valid ||
        !['optimal', 'feasible'].includes(report.solution.status)
    )
        throw new Error('Composition non vérifiée ; aucun placement.');
    if (!placement || placement.issues.length)
        throw new Error(placement?.issues.join(' ') || 'Relever le club avant le placement.');
    const assignments = report.solution.assignments ?? [];
    if (
        !assignments.length ||
        placement.cards.length !== assignments.length ||
        assignments.length > 11 ||
        new Set(placement.cards.map((c) => c.slot)).size !== assignments.length ||
        placement.cards.some(
            (c) =>
                !assignments.some(
                    (a) => a.slot === c.slot && a.candidate_key === c.candidate_key,
                ) ||
                !report.selected_candidates.some(
                    (s) =>
                        s.key === c.candidate_key &&
                        s.card_id === c.card_id &&
                        s.owned &&
                        !s.protected,
                ),
        )
    )
        throw new Error('Le plan ne correspond pas aux exemplaires calculés.');
    const initial = await activeContext(signal);
    const deadline = Date.now() + 120000;
    let steps = 0;
    if (
        initial.tabId !== proposal.context.tabId ||
        initial.documentId !== proposal.context.documentId ||
        initial.viewport.href !== proposal.context.viewport.href
    )
        throw new Error('L’onglet a changé depuis le calcul.');
    async function observe(command?: Command) {
        if (Date.now() > deadline || (command && ++steps > 250))
            throw new Error('Limite de navigation atteinte ; vérifier la composition.');
        const context = await activeContext(signal);
        if (
            context.tabId !== initial.tabId ||
            context.documentId !== initial.documentId ||
            context.viewport.href !== initial.viewport.href
        )
            throw new Error('L’onglet EA a changé ; arrêt.');
        signal.throwIfAborted();
        const results = await chrome.scripting.executeScript({
            target: { tabId: initial.tabId, documentIds: [initial.documentId] },
            func: placementInTab,
            args: command ? [command] : [],
        });
        signal.throwIfAborted();
        const response = results.find((r) => r.frameId === 0);
        if (!response?.result || response.documentId !== initial.documentId)
            throw new Error('Écran de placement indisponible.');
        return response.result;
    }
    let state = await observe();
    // Chrome peut réordonner les clés des objets renvoyés par executeScript.
    const boardKey = (b: PreparedSbc['board']) =>
        JSON.stringify([b.title, b.requirements, b.positions, b.slot_indices]);
    const board = boardKey(proposal.board);
    if (boardKey(state.board) !== board) throw new Error('Le SBC a changé depuis le calcul.');
    if (
        JSON.stringify(state.board.positions) !== JSON.stringify(report.challenge.positions) ||
        state.slots.some((s) => s.card)
    )
        throw new Error('Ouvrir une composition vide correspondant à ce SBC.');
    const filled = new Map<number, NonNullable<(typeof state.slots)[number]['card']>>();
    function check() {
        if (
            boardKey(state.board) !== board ||
            state.slots.some(
                (s) => JSON.stringify(s.card) !== JSON.stringify(filled.get(s.index) ?? null),
            )
        )
            throw new Error('Le SBC ou sa composition a changé ; arrêt.');
    }
    async function step(action: Command['action'], card: PlacementCard) {
        check();
        await observe({ action, card, signature: state.signature });
        const previous = state.signature,
            deadline = Date.now() + 8000;
        do {
            await new Promise((resolve) => setTimeout(resolve, 250));
            state = await observe();
            const ready =
                action === 'place'
                    ? !!state.slots[card.slot]?.card?.rating &&
                      !!state.slots[card.slot]?.card?.club_id &&
                      !!state.slots[card.slot]?.card?.league_id &&
                      !!state.slots[card.slot]?.card?.nation_id
                    : action === 'open'
                      ? state.selected === card.slot && state.stage !== 'squad'
                      : action === 'clear-position'
                        ? state.stage === 'filters' && state.position_filter === 'Position'
                        : action === 'club'
                          ? state.stage === 'filters'
                          : state.stage === 'results' &&
                            state.rows.length > 0 &&
                            state.rows.every(
                                (r) =>
                                    r.name &&
                                    r.rating > 0 &&
                                    Object.keys(r.stats).length === 6 &&
                                    Object.values(r.stats).every(Number.isInteger),
                            );
            if (state.signature !== previous && ready) return;
        } while (Date.now() < deadline);
        throw new Error('Écran inchangé après action ; arrêt sans répétition.');
    }
    try {
        for (const card of [...placement.cards].sort((a, b) => a.slot - b.slot)) {
            const fresh = await loadWorkspace(base, signal);
            if (fresh.revision !== proposal.revision || fresh.mode !== 'local')
                throw new Error('Inventaire modifié ; recalculer.');
            progress(`Placement ${filled.size + 1}/${assignments.length} : ${card.reading.name}…`);
            if (state.selected !== card.slot || state.stage === 'squad') await step('open', card);
            if (state.stage === 'details') await step('club', card);
            if (state.stage === 'filters' && report.challenge.position_mode === 'any') {
                if (state.position_filter === null)
                    throw new Error('Filtre de poste illisible ; arrêt.');
                if (state.position_filter !== 'Position') await step('clear-position', card);
            }
            if (state.stage === 'filters') await step('search', card);
            if (state.stage !== 'results') throw new Error('Recherche du club indisponible.');
            const seen = new Set<string>();
            for (let page = 0; page < 100; page++) {
                check();
                const signature = JSON.stringify(state.rows);
                if (seen.has(signature)) throw new Error('Page du club répétée ; arrêt.');
                seen.add(signature);
                if (
                    state.rows.some(
                        (r) => r.name === card.reading.name && r.rating === card.reading.rating,
                    )
                )
                    break;
                if (!state.hasNext || page === 99)
                    throw new Error(`Carte introuvable : ${card.reading.name}.`);
                await step('next', card);
            }
            if ((await loadWorkspace(base, signal)).revision !== proposal.revision)
                throw new Error('Inventaire modifié ; recalculer.');
            await step('place', card);
            const actual = state.slots[card.slot]?.card;
            if (
                !actual ||
                actual.rating !== card.reading.rating ||
                ['nation_id', 'league_id', 'club_id'].some(
                    (k) => actual[k as 'nation_id'] !== card.reading[k as 'nation_id'],
                )
            )
                throw new Error(
                    'Carte placée non confirmée ; vérifier la composition manuellement.',
                );
            filled.set(card.slot, actual);
            check();
        }
    } catch (error) {
        if (!filled.size) throw error;
        throw new Error(
            `Arrêt après ${filled.size} placement(s). ${error instanceof Error ? error.message : 'Action impossible.'} Vérifie la composition manuellement.`,
        );
    }
    return filled.size;
}
