// Consultation locale des états exportés. Aucun code EA, réseau ou stockage de session.
const page = document.documentElement.dataset.simulationPage;
const go = (name) => { location.href = `${name}.html`; };
for (const canvas of document.querySelectorAll('canvas[data-sim-canvas]')) {
    const image = new Image();
    image.onload = () => canvas.getContext('2d')?.drawImage(image, 0, 0, canvas.width, canvas.height);
    image.src = canvas.dataset.simCanvas;
}
function restoreScroll() {
    for (const node of document.querySelectorAll('[data-sim-scroll-top], [data-sim-scroll-left]')) {
        node.scrollTop = Number(node.dataset.simScrollTop || 0);
        node.scrollLeft = Number(node.dataset.simScrollLeft || 0);
    }
}
addEventListener('load', () => { restoreScroll(); setTimeout(restoreScroll, 150); });
const hud = document.createElement('aside');
hud.id = 'simulation-notice';
hud.innerHTML = '<a href="../index.html">← Tous les écrans</a><span>Référence locale · navigation entre captures</span>';
document.body.append(hud);
if (new URLSearchParams(location.search).has('reference')) hud.hidden = true;
const parents = {
    'club': 'home', 'club-joueurs': 'club', 'club-joueurs-page-2': 'club-joueurs',
    'club-filtres': 'club-joueurs', 'joueur-fiche': 'club-joueurs',
    'sbc-liste': 'home', 'sbc-groupe': 'sbc-liste', 'sbc-score': 'sbc-groupe',
    'sbc-quotidien': 'sbc-liste', 'sbc-cinq-joueurs': 'sbc-liste', 'sbc-onze-joueurs': 'sbc-liste',
    'sbc-case-vide': 'sbc-quotidien', 'sbc-recherche': 'sbc-case-vide',
    'sbc-resultats': 'sbc-recherche', 'sbc-zone-travail': 'sbc-resultats',
};
document.addEventListener('click', (event) => {
    const target = event.target instanceof Element ? event.target : null;
    if (!target || target.closest('#simulation-notice')) return;
    event.preventDefault();
    const text = target.closest('button')?.textContent.trim();
    if (target.closest('.icon-home')) return go('home');
    if (target.closest('.icon-club')) return go('club');
    if (target.closest('.icon-sbc')) return go('sbc-liste');
    if (target.closest('.players-tile')) return go('club-joueurs');
    if (target.closest('.ut-navigation-button-control')) return go(parents[page] || 'home');
    const tile = target.closest('.tile, .ut-sbc-set-tile-view');
    const title = tile?.querySelector('.tileTitle')?.textContent.trim();
    if (title === 'Daily Login Upgrade') return go('sbc-quotidien');
    if (title === '2x 80+ Upgrade') return go('sbc-cinq-joueurs');
    if (title === '10x 82+ Upgrade') return go('sbc-onze-joueurs');
    if (title === 'LALIGA & Liga F') return go('sbc-groupe');
    if (text === 'Start Challenge' && page === 'sbc-groupe') return go('sbc-score');
    if (text === 'Player Bio') return go('joueur-fiche');
    if (text === 'Add Player') return go('sbc-recherche');
    if (text === 'Search') {
        if (page === 'club-filtres') return go('club-joueurs');
        return go(page.startsWith('sbc-') ? 'sbc-resultats' : 'club-filtres');
    }
    if (target.closest('button.pagination.next') && page === 'club-joueurs') return go('club-joueurs-page-2');
    if (target.closest('button.pagination.prev') && page === 'club-joueurs-page-2') return go('club-joueurs');
    if (target.closest('button.workTab')) return go('sbc-zone-travail');
    const slot = target.closest('.ut-squad-slot-view');
    if (slot && !slot.classList.contains('locked') && Number(slot.getAttribute('index')) < 11) return go('sbc-case-vide');
    const row = target.closest('li.listFUTItem');
    if (row && !target.closest('button.btnAction.add')) {
        for (const r of row.parentElement.children) r.classList.remove('selected');
        row.classList.add('selected');
        return;
    }
    // Les captures ne contiennent pas les gestionnaires métier de l'application.
    if (target.closest('button, .tile')) {
        hud.hidden = false;
        hud.lastElementChild.textContent = 'État figé : interaction à implémenter dans le simulateur.';
    }
});
