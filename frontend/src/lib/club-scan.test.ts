// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { clubPageInTab, scanClub, sbcInTab } from './club-scan';
import { activeContext, captureActiveTab } from './tab-capture';
import { analyzeImage } from './api';

vi.mock('./tab-capture', () => ({ activeContext: vi.fn(), captureActiveTab: vi.fn() }));
vi.mock('./api', () => ({ analyzeImage: vi.fn() }));
beforeEach(() => {
    vi.stubGlobal('location', {
        hostname: 'www.ea.com',
        pathname: '/ea-sports-fc/ultimate-team/web-app/',
    });
    document.body.innerHTML = `<h1 class="title">My Club Players</h1><div><ul class="paginated">${Array.from(
        { length: 6 },
        (_, i) => `
        <li class="listFUTItem" data-row="${i}"><div class="entityContainer">
        <div class="player item ${i === 1 ? 'loan' : ''}"><div class="playerOverview"><div class="rating">83</div><div class="position">CM</div></div></div>
        <div class="name">Joueur fictif ${i}</div><div class="player-stats-data-component"><ul>${['PAC', 'SHO', 'PAS', 'DRI', 'DEF', 'PHY'].map((label) => `<li><span class="label">${label}</span><span class="value">70</span></li>`).join('')}</ul></div>
        <img src="https://www.ea.com/images/flags/dark/45.png"></div></li>`,
    ).join('')}</ul></div>
        <button class="pagination prev" style="display:none">Previous</button><button class="pagination next">Next</button><button id="submit">Submit</button>`;
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (
        this: HTMLElement,
    ) {
        return this.classList.contains('listFUTItem')
            ? new DOMRect(0, Number(this.dataset.row) * 40, 100, 30)
            : new DOMRect(0, 0, 200, 120);
    });
});
afterEach(() => {
    document.body.innerHTML = '';
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
});

it('lit toutes les lignes HTML, sépare visibilité/prêts et ne déduit aucun identifiant EA', () => {
    const page = clubPageInTab();
    expect(page.cards).toHaveLength(6);
    expect(page.cards.filter((c) => c.visible)).toHaveLength(3);
    expect(page.cards[5]).toMatchObject({
        name: 'Joueur fictif 5',
        rating: 83,
        nation_id: 45,
        visible: false,
        loan: false,
    });
    expect(page.cards[1].loan).toBe(true);
    expect(page.cards[0]).not.toHaveProperty('confidence');
    expect(page.cards[0]).not.toHaveProperty('instance_id');
});

it('ne clique que Suivant et refuse une page modifiée', () => {
    const next = vi.fn(),
        submit = vi.fn();
    document.querySelector('.next')!.addEventListener('mouseup', next);
    document.querySelector('#submit')!.addEventListener('mouseup', submit);
    expect(() => clubPageInTab('ancienne-page')).toThrow('changé');
    expect(next).not.toHaveBeenCalled();
    clubPageInTab(clubPageInTab().signature);
    expect(next).toHaveBeenCalledOnce();
    expect(submit).not.toHaveBeenCalled();
});

it('refuse les autres écrans et une ligne encore incomplète', () => {
    document.querySelector('h1')!.textContent = 'SBC';
    expect(() => clubPageInTab()).toThrow('Club');
    document.querySelector('h1')!.textContent = 'My Club Players';
    document.querySelector('.rating')!.textContent = '';
    expect(() => clubPageInTab()).toThrow('incomplète');
});

it('lit toutes les conditions du SBC courant une seule fois et sans cliquer sur un échange', () => {
    const rules = '<li>Rare players: Min. 1</li><li>Number of Players: 3</li>';
    document.body.innerHTML = `<ul class="sbc-requirements-checklist"></ul><ul class="sbc-requirements-checklist">${rules}</ul><ul class="sbc-requirements-checklist">${rules}</ul>${['ST', 'CM', 'CAM'].map((p) => `<div class="ut-squad-slot-pedestal-view"><span class="label">${p}</span></div>`).join('')}<button>Submit</button>`;
    const click = vi.fn();
    document.querySelector('button')!.addEventListener('click', click);
    expect(sbcInTab()).toEqual({
        source: 'dom',
        requirements: 'Rare players: Min. 1\nNumber of Players: 3',
        positions: ['ST', 'CM', 'CAM'],
    });
    expect(click).not.toHaveBeenCalled();
    document.querySelectorAll('.sbc-requirements-checklist').forEach((e) => e.remove());
    expect(() => sbcInTab()).toThrow('conditions');
});

function controller() {
    const first = clubPageInTab(),
        last = structuredClone(first);
    last.cards[0].name = 'Autre joueur fictif';
    last.signature = 'page-2';
    last.has_previous = true;
    last.has_next = false;
    let current = first;
    vi.mocked(activeContext).mockResolvedValue({
        tabId: 1,
        documentId: 'document-ea',
        viewport: { href: 'https://www.ea.com/ea-sports-fc/ultimate-team/web-app/' },
    } as Awaited<ReturnType<typeof activeContext>>);
    vi.mocked(captureActiveTab).mockResolvedValue({
        file: new File(['synthetic'], 'synthetic.png', { type: 'image/png' }),
        url: 'blob:synthetic',
        width: 200,
        height: 120,
    } as Awaited<ReturnType<typeof captureActiveTab>>);
    vi.mocked(analyzeImage).mockResolvedValue({ ocr: null } as Awaited<
        ReturnType<typeof analyzeImage>
    >);
    URL.revokeObjectURL = vi.fn();
    const execute = vi.fn(async (options: { args: string[] }) => {
        const result = current;
        if (options.args.length) current = last;
        return [{ frameId: 0, documentId: 'document-ea', result }];
    });
    vi.stubGlobal('chrome', { scripting: { executeScript: execute } });
    return execute;
}

it('parcourt deux pages, conserve les lignes DOM sans les compter comme OCR et s’arrête à la fin', async () => {
    const execute = controller();
    const result = await scanClub('http://localhost', new AbortController().signal, vi.fn(), 10);
    expect(result.complete).toBe(true);
    expect(result.pages).toHaveLength(2);
    expect(result.pages[0].cards[0].reading).not.toHaveProperty('confidence');
    expect(result.pages[0].ocr).toBeNull();
    expect(execute.mock.calls.filter(([o]) => o.args.length)).toHaveLength(1);
});

it('une limite de pages renvoie un scan partiel et ne clique pas Suivant', async () => {
    const execute = controller();
    const result = await scanClub('http://localhost', new AbortController().signal, vi.fn(), 1);
    expect(result.complete).toBe(false);
    expect(result.pages).toHaveLength(1);
    expect(execute.mock.calls.every(([o]) => o.args.length === 0)).toBe(true);
});
