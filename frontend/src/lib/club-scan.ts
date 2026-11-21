import { analyzeImage, type Perception } from './api';
import { activeContext, captureActiveTab, type TabCapture } from './tab-capture';
import { requestJson } from './api';
import { solveWorkspace, type Workspace } from './sbc-api';
import type { SolverReport } from './sbc-report';
import type { PreparedSbc } from './sbc-fill';

export type DomCard = {
    name: string;
    rating: number;
    position: string;
    stats: Record<string, number>;
    nation_id: number | null;
    league_id: number | null;
    club_id: number | null;
    visible: boolean;
    loan: boolean;
    active: boolean;
    rarity: string;
};
type Page = { cards: DomCard[]; has_previous: boolean; has_next: boolean; signature: string };
export type ClubScan = {
    capture_id: string;
    complete: boolean;
    pages: Array<{
        cards: Array<{
            reading: Omit<DomCard, 'visible' | 'loan' | 'active' | 'rarity'> & {
                capture_id: string;
                element_id: string;
            };
            visible: boolean;
            loan: boolean;
            active?: boolean;
            rarity?: string;
        }>;
        has_previous: boolean;
        has_next: boolean;
        ocr: Perception['ocr'];
        ocr_error: string | null;
    }>;
};

// Rejoindre le club depuis n'importe quel écran EA, sans toucher à la composition.
export function clubNavigationInTab(expected?: string) {
    if (
        !['ea.com', 'www.ea.com'].includes(location.hostname) ||
        !location.pathname.includes('/ultimate-team/web-app/')
    )
        return { ready: false, signature: '', error: 'Ouvrir la Web App EA en anglais.' };
    const title = document.querySelector('h1.title')?.textContent?.trim();
    const visible = (e: Element | null) =>
        !!e &&
        !e.hasAttribute('disabled') &&
        e.getAttribute('aria-disabled') !== 'true' &&
        !e.classList.contains('disabled') &&
        getComputedStyle(e).display !== 'none' &&
        e.getBoundingClientRect().width > 0;
    const players = Array.from(document.querySelectorAll('h1.tileHeader')).find(
        (e) => e.textContent?.trim() === 'Players',
    );
    const previous = document.querySelector('button.pagination.prev');
    const inClub = title === 'My Club Players';
    const rows = Array.from(document.querySelectorAll('ul.paginated > li.listFUTItem'));
    const ready =
        inClub &&
        rows.length > 0 &&
        !visible(previous) &&
        rows.every(
            (row) =>
                !!row.querySelector('.entityContainer > .name')?.textContent?.trim() &&
                /^[1-9]\d?$/.test(row.querySelector('.rating')?.textContent?.trim() ?? '') &&
                row.querySelectorAll('.player-stats-data-component .value').length === 6 &&
                Array.from(row.querySelectorAll('.player-stats-data-component .value')).every((v) =>
                    /^\d{1,2}$/.test(v.textContent?.trim() ?? ''),
                ),
        );
    const button = inClub
        ? visible(previous)
            ? previous
            : null
        : players
          ? (players.parentElement?.parentElement ?? null)
          : title === 'Club'
            ? null
            : document.querySelector('button.ut-tab-bar-item.icon-club');
    const signature = JSON.stringify([
        title,
        !!players,
        ready,
        document.querySelector('ul.paginated')?.textContent ?? '',
    ]);
    if (expected !== undefined) {
        if (expected !== signature || !visible(button))
            return { ready: false, signature, error: 'Le club a changé ; relancer le scan.' };
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
    }
    return { ready, signature, canAdvance: visible(button), error: '' };
}

// Cette fonction est injectée seule dans la page : uniquement DOM, aucun état interne EA.
export function clubPageInTab(advanceFrom?: string): Page {
    if (
        !['ea.com', 'www.ea.com'].includes(location.hostname) ||
        !location.pathname.includes('/ultimate-team/web-app/') ||
        document.querySelector('h1.title')?.textContent !== 'My Club Players'
    )
        throw new Error('Ouvrir « Club → Players » dans la Web App EA en anglais.');
    const list = document.querySelector('ul.paginated');
    const rows = Array.from(list?.querySelectorAll(':scope > li.listFUTItem') ?? []);
    if (!rows.length) throw new Error('Attendre le chargement des joueurs du club.');
    const clip = list!.parentElement!.getBoundingClientRect();
    const cards = rows.map((row): DomCard => {
        const text = (selector: string) => row.querySelector(selector)?.textContent?.trim() ?? '';
        const name = text('.entityContainer > .name');
        const rating = text('.playerOverview .rating');
        const position = text('.playerOverview .position');
        const stats = Object.fromEntries(
            Array.from(row.querySelectorAll('.player-stats-data-component li')).map((e) => [
                e.querySelector('.label')?.textContent?.trim() ?? '',
                /^\d{1,2}$/.test(e.querySelector('.value')?.textContent?.trim() ?? '')
                    ? Number(e.querySelector('.value')?.textContent)
                    : NaN,
            ]),
        );
        if (
            !name ||
            !/^[1-9]\d?$/.test(rating) ||
            !position ||
            Object.keys(stats).length !== 6 ||
            Object.entries(stats).some(
                ([key, n]) =>
                    !/^(PAC|SHO|PAS|DRI|DEF|PHY|DIV|HAN|KIC|REF|SPD|POS)$/.test(key) ||
                    !Number.isInteger(n) ||
                    n < 0 ||
                    n > 99,
            )
        )
            throw new Error('Une ligne de joueurs est incomplète ; attendre son chargement.');
        const logo = (kind: string) => {
            const image = Array.from(row.querySelectorAll('img')).find((i) =>
                i.src.includes(`/${kind}/`),
            );
            const id = image?.src.match(/\/(\d+)\.png(?:\?.*)?$/)?.[1];
            return id ? Number(id) : null;
        };
        const box = row.getBoundingClientRect();
        return {
            name,
            rating: Number(rating),
            position,
            stats,
            nation_id: logo('flags'),
            league_id: logo('leagues'),
            club_id: logo('clubs'),
            visible:
                box.width > 0 &&
                box.top >= Math.max(0, clip.top) &&
                box.bottom <= Math.min(innerHeight, clip.bottom),
            loan: !!row.querySelector('.player.item.loan'),
            active:
                row.classList.contains('is-active') ||
                !!row.querySelector('.ut-list-active-tag-view'),
            rarity: row.querySelector('.player.item.specials') ? 'Spéciales (type non lu)' : 'Base',
        };
    });
    const available = (selector: string) => {
        const b = document.querySelector<HTMLButtonElement>(selector);
        return (
            !!b &&
            !b.disabled &&
            b.getAttribute('aria-disabled') !== 'true' &&
            !b.classList.contains('disabled') &&
            getComputedStyle(b).display !== 'none' &&
            getComputedStyle(b).visibility !== 'hidden' &&
            b.getBoundingClientRect().width > 0
        );
    };
    const page = {
        cards,
        signature: JSON.stringify(cards),
        has_previous: available('button.pagination.prev'),
        has_next: available('button.pagination.next'),
    };
    if (advanceFrom !== undefined) {
        if (advanceFrom !== page.signature || !page.has_next)
            throw new Error('La page du club a changé ; arrêt du parcours.');
        // Seul « Suivant » est autorisé ici ; aucun placement, achat ou bouton SBC.
        const button = document.querySelector<HTMLButtonElement>('button.pagination.next')!;
        const box = button.getBoundingClientRect();
        for (const type of ['mousedown', 'mouseup', 'click'])
            button.dispatchEvent(
                new MouseEvent(type, {
                    bubbles: true,
                    button: 0,
                    clientX: box.x + box.width / 2,
                    clientY: box.y + box.height / 2,
                }),
            );
    }
    return page;
}

// Lire la rareté dans la fiche affichée : sélection, fiche, retour, aucun transfert.
export function clubBioInTab(command?: string) {
    if (
        !['ea.com', 'www.ea.com'].includes(location.hostname) ||
        !location.pathname.includes('/ultimate-team/web-app/')
    )
        throw new Error('Ouvrir le club EA.');
    const rows = Array.from(document.querySelectorAll<HTMLElement>('ul.paginated>li.listFUTItem'));
    const bio = document.querySelector('.ut-player-bio-view');
    const rarity =
        Array.from(bio?.querySelectorAll('.ut-item-bio-row-view') ?? [])
            .find((e) => e.querySelector('h1')?.textContent?.trim() === 'Rarity')
            ?.querySelector('h2')
            ?.textContent?.trim() ?? '';
    const selected = rows.findIndex((e) => e.classList.contains('selected'));
    const state = { bio: !!bio, rarity, selected };
    const signature = JSON.stringify([
        state,
        rows.map((e) => e.querySelector('.entityContainer>.name')?.textContent),
    ]);
    if (command) {
        const { action, index, expected } = JSON.parse(command);
        if (expected !== signature) throw new Error('Le club a changé pendant la lecture du type.');
        const button =
            action === 'select' && !bio
                ? rows[index]
                : action === 'open' && !bio && selected === index
                  ? Array.from(document.querySelectorAll('button')).find(
                        (b) => b.textContent?.trim() === 'Player Bio',
                    )
                  : action === 'close' && bio
                    ? bio.closest('section')?.querySelector('button.ut-navigation-button-control')
                    : null;
        if (!button || button.getBoundingClientRect().width === 0)
            throw new Error('Fiche de rareté indisponible.');
        const box = button.getBoundingClientRect();
        for (const type of ['mousedown', 'mouseup', 'click'])
            button.dispatchEvent(
                new MouseEvent(type, {
                    bubbles: true,
                    button: 0,
                    clientX: box.x + box.width / 2,
                    clientY: box.y + box.height / 2,
                }),
            );
    }
    return { ...state, signature };
}

export async function scanClub(
    base: string,
    signal: AbortSignal,
    progress: (message: string) => void,
    maxPages = 100,
    onPage?: (scan: ClubScan) => void,
): Promise<ClubScan> {
    signal.throwIfAborted();
    if (!Number.isInteger(maxPages) || maxPages < 1 || maxPages > 500)
        throw new Error('Limiter le parcours entre 1 et 500 pages.');
    const initial = await activeContext(signal);
    async function execute<T>(func: (...args: string[]) => T, args: string[] = []) {
        const context = await activeContext(signal);
        if (
            context.tabId !== initial.tabId ||
            context.documentId !== initial.documentId ||
            context.viewport.href !== initial.viewport.href
        )
            throw new Error('L’onglet EA a changé ; arrêt du parcours.');
        const results = await chrome.scripting.executeScript({
            target: { tabId: initial.tabId, documentIds: [initial.documentId] },
            func,
            args,
        });
        signal.throwIfAborted();
        const result = results.find((r) => r.frameId === 0);
        if (!result?.result || result.documentId !== initial.documentId)
            throw new Error(
                'Lecture du club impossible. Ouvrir « Club → Players » et attendre le chargement.',
            );
        return result.result;
    }
    const deadline = Date.now() + 60000;
    let navigation = await execute(clubNavigationInTab);
    while (!navigation.ready) {
        if (navigation.error) throw new Error(navigation.error);
        if (Date.now() >= deadline) throw new Error('Le club ne se charge pas ; relancer le scan.');
        progress('Ouverture du club et retour à la première page…');
        const signature = navigation.signature;
        if (navigation.canAdvance) await execute(clubNavigationInTab, [signature]);
        do {
            await new Promise((resolve) => setTimeout(resolve, 300));
            signal.throwIfAborted();
            navigation = await execute(clubNavigationInTab);
            if (navigation.error) throw new Error(navigation.error);
        } while (navigation.signature === signature && Date.now() < deadline);
    }
    const read = (advanceFrom?: string) =>
        execute(clubPageInTab, advanceFrom === undefined ? [] : [advanceFrom]);
    let page = await read();
    if (page.has_previous) throw new Error('Revenir à la première page du club avant le scan.');
    const scan: ClubScan = { capture_id: crypto.randomUUID(), complete: false, pages: [] };
    const seen = new Set<string>();
    let captureFailure: string | null = null;
    for (let n = 1; n <= maxPages; n++) {
        signal.throwIfAborted();
        if (seen.has(page.signature)) throw new Error('Page répétée ; arrêt du parcours.');
        seen.add(page.signature);
        progress(`Page ${n} : ${page.cards.length} cartes HTML, lecture des cartes visibles…`);
        let ocr: Perception['ocr'] = null,
            ocrError: string | null = null;
        let capture: TabCapture | undefined;
        try {
            if (captureFailure) throw new Error(captureFailure);
            try {
                capture = await captureActiveTab(signal);
            } catch (error) {
                captureFailure = error instanceof Error ? error.message : 'Capture indisponible.';
                throw error;
            }
            const response = await analyzeImage(base, capture.file, capture, signal);
            ocr = response.ocr ?? null;
            if (!ocr) ocrError = 'Aucune région de carte lue par l’OCR.';
        } catch (error) {
            signal.throwIfAborted();
            ocrError = error instanceof Error ? error.message : 'OCR indisponible.';
        } finally {
            if (capture) URL.revokeObjectURL(capture.url);
        }
        if ((await read()).signature !== page.signature)
            throw new Error('Le club a changé pendant la capture.');
        const rarities = page.cards.map((c) => c.rarity);
        let bio = await execute(clubBioInTab);
        async function bioStep(action: string, index: number) {
            await execute(clubBioInTab, [
                JSON.stringify({ action, index, expected: bio.signature }),
            ]);
            const until = Date.now() + 3000;
            do {
                await new Promise((resolve) => setTimeout(resolve, 100));
                bio = await execute(clubBioInTab);
                if (
                    action === 'select'
                        ? bio.selected === index
                        : action === 'open'
                          ? bio.bio && !!bio.rarity
                          : !bio.bio
                )
                    return;
            } while (Date.now() < until);
            throw new Error('La fiche du joueur ne se charge pas.');
        }
        if (bio.bio) await bioStep('close', 0);
        for (const [i, card] of page.cards.entries()) {
            if (card.loan || card.rarity === 'Base') continue;
            progress(`Page ${n} : lecture du type de ${card.name}…`);
            await bioStep('select', i);
            await bioStep('open', i);
            rarities[i] = bio.rarity.slice(0, 100);
            await bioStep('close', i);
        }
        if ((await read()).signature !== page.signature)
            throw new Error('Le club a changé pendant la lecture des types.');
        scan.pages.push({
            cards: page.cards.map(({ visible, loan, active, rarity: _, ...reading }, i) => ({
                reading: {
                    ...reading,
                    capture_id: scan.capture_id,
                    element_id: `page-${n}-row-${i + 1}`,
                },
                visible,
                loan,
                active,
                rarity: rarities[i],
            })),
            has_previous: page.has_previous,
            has_next: page.has_next,
            ocr,
            ocr_error: ocrError,
        });
        onPage?.({ ...scan, pages: [...scan.pages] });
        if (!page.has_next) {
            scan.complete = true;
            return scan;
        }
        if (n === maxPages) return scan;
        const previous = page.signature;
        await read(previous);
        const deadline = Date.now() + 15000;
        while (Date.now() < deadline) {
            await new Promise((resolve) => setTimeout(resolve, 300));
            signal.throwIfAborted();
            try {
                page = await read();
            } catch {
                continue;
            }
            if (page.signature !== previous) break;
        }
        if (page.signature === previous) throw new Error('La page suivante ne se charge pas.');
    }
    return scan;
}

// Le SBC courant est lu dans le DOM ; cette lecture n'est pas comptée comme un résultat OCR.
export function sbcInTab() {
    if (
        !['ea.com', 'www.ea.com'].includes(location.hostname) ||
        !location.pathname.includes('/ultimate-team/web-app/')
    )
        return { error: 'Ouvrir un SBC dans la Web App EA.' };
    const checklist = Array.from(document.querySelectorAll('.sbc-requirements-checklist')).find(
        (e) => e.children.length > 0,
    );
    const slots = Array.from(document.querySelectorAll('.ut-squad-slot-view')).filter(
        (e) =>
            !e.classList.contains('locked') &&
            e.getBoundingClientRect().width > 0 &&
            /^(?:\d|10)$/.test(e.getAttribute('index') ?? '') &&
            /^[A-Z]{2,3}$/.test(
                e.querySelector('.ut-squad-slot-pedestal-view .label')?.textContent?.trim() ?? '',
            ),
    );
    const positions = slots.map((e) =>
        e.querySelector('.ut-squad-slot-pedestal-view .label')!.textContent!.trim(),
    );
    const slot_indices = slots.map((e) => Number(e.getAttribute('index')));
    const requirements = checklist
        ? Array.from(checklist.children)
              .map((e) => e.textContent?.trim())
              .join('\n')
        : '';
    if (
        !requirements ||
        !positions.length ||
        positions.length > 11 ||
        new Set(slot_indices).size !== positions.length
    )
        return { error: 'Ouvrir l’écran de composition et afficher les conditions du SBC.' };
    return {
        source: 'dom',
        requirements,
        positions,
        slot_indices,
        title: document.querySelector('h1.title')?.textContent?.trim() ?? '',
    };
}

export async function prepareSbc(
    base: string,
    workspace: Workspace,
    budget: number,
    cap: number,
    signal: AbortSignal,
    progress: (message: string) => void,
): Promise<PreparedSbc> {
    progress('Lecture des conditions du SBC…');
    const context = await activeContext(signal);
    const results = await chrome.scripting.executeScript({
        target: { tabId: context.tabId, documentIds: [context.documentId] },
        func: sbcInTab,
    });
    const observed = results.find((r) => r.frameId === 0)?.result;
    if (!observed) throw new Error('Aucune condition lisible sur cet écran.');
    if ('error' in observed) throw new Error(observed.error);
    const reading = (await requestJson(
        base,
        '/api/v1/sbc/read',
        {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                source: observed.source,
                requirements: observed.requirements,
                positions: observed.positions,
                budget,
                market: 'pc',
            }),
        },
        signal,
        15000,
    )) as { ready: boolean; challenge: SolverReport['challenge']; issues: string[] };
    if (!reading.ready || !reading.challenge)
        throw new Error('Conditions à relire : ' + reading.issues.join(' ; '));
    progress('Recherche avec les cartes du club, puis les achats si nécessaire…');
    const result = await solveWorkspace(
        base,
        { ...workspace, challenge: { ...reading.challenge, max_card_value: cap } },
        budget,
        signal,
        true,
    );
    return {
        ...result,
        context,
        board: {
            title: observed.title,
            requirements: observed.requirements,
            positions: observed.positions,
            slot_indices: observed.slot_indices,
        },
    };
}
