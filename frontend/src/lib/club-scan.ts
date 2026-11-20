import { analyzeImage, type Perception } from './api';
import { activeContext, captureActiveTab } from './tab-capture';

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
};
type Page = { cards: DomCard[]; has_previous: boolean; has_next: boolean; signature: string };
export type ClubScan = {
    capture_id: string;
    complete: boolean;
    pages: Array<{
        cards: Array<{
            reading: Omit<DomCard, 'visible' | 'loan'> & { capture_id: string; element_id: string };
            visible: boolean;
            loan: boolean;
        }>;
        has_previous: boolean;
        has_next: boolean;
        ocr: Perception['ocr'];
        ocr_error: string | null;
    }>;
};

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
    async function read(advanceFrom?: string) {
        const context = await activeContext(signal);
        if (
            context.tabId !== initial.tabId ||
            context.documentId !== initial.documentId ||
            context.viewport.href !== initial.viewport.href
        )
            throw new Error('L’onglet EA a changé ; arrêt du parcours.');
        const results = await chrome.scripting.executeScript({
            target: { tabId: initial.tabId, documentIds: [initial.documentId] },
            func: clubPageInTab,
            args: advanceFrom === undefined ? [] : [advanceFrom],
        });
        signal.throwIfAborted();
        const result = results.find((r) => r.frameId === 0);
        if (!result?.result || result.documentId !== initial.documentId)
            throw new Error('Lecture du club impossible.');
        return result.result;
    }
    let page = await read();
    if (page.has_previous) throw new Error('Revenir à la première page du club avant le scan.');
    const scan: ClubScan = { capture_id: crypto.randomUUID(), complete: false, pages: [] };
    const seen = new Set<string>();
    for (let n = 1; n <= maxPages; n++) {
        signal.throwIfAborted();
        if (seen.has(page.signature)) throw new Error('Page répétée ; arrêt du parcours.');
        seen.add(page.signature);
        progress(`Page ${n} : ${page.cards.length} cartes HTML, lecture des cartes visibles…`);
        let ocr: Perception['ocr'] = null,
            ocrError: string | null = null;
        const capture = await captureActiveTab(signal);
        try {
            const response = await analyzeImage(base, capture.file, capture, signal);
            ocr = response.ocr ?? null;
            if (!ocr) ocrError = 'Aucune région de carte lue par l’OCR.';
        } catch (error) {
            signal.throwIfAborted();
            ocrError = error instanceof Error ? error.message : 'OCR indisponible.';
        } finally {
            URL.revokeObjectURL(capture.url);
        }
        if ((await read()).signature !== page.signature)
            throw new Error('Le club a changé pendant la capture.');
        scan.pages.push({
            cards: page.cards.map(({ visible, loan, ...reading }, i) => ({
                reading: {
                    ...reading,
                    capture_id: scan.capture_id,
                    element_id: `page-${n}-row-${i + 1}`,
                },
                visible,
                loan,
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
