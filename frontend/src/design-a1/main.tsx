import { StrictMode, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { StadiumBrand, StadiumIcon, StadiumPitch, type PitchPlacement } from './StadiumKit';
import charcoal from './assets/charcoal-surface.png';
import grass from './assets/pitch-grass.png';
import gold from './assets/card-gold-sketch.svg';
import portrait from './assets/player-silhouette.svg';
import mark from './assets/brand-mark.svg';
import lines from './assets/pitch-lines.svg';
import mask from './assets/card-mask.svg';
import './preview.css';

// Données exclusivement fictives pour contrôler le rendu de onze cartes, sans appel API.
const setup: [string, string, number, string, 'club' | 'purchase', number, number, number][] = [
    ['demo-lw', 'Sacha Exemple', 83, 'LW', 'club', 800, 27, 18],
    ['demo-st', 'Léa Fictive', 84, 'ST', 'club', 800, 50, 18],
    ['demo-rw', 'Noa Exemple', 83, 'RW', 'club', 800, 73, 18],
    ['demo-cm-l', 'Morgan Test', 82, 'CM', 'purchase', 1700, 27, 43],
    ['demo-cm', 'Alex Exemple', 83, 'CM', 'club', 800, 50, 43],
    ['demo-cm-r', 'Eli Test', 82, 'CM', 'purchase', 2500, 73, 43],
    ['demo-lb', 'Inès Démo', 82, 'LB', 'club', 800, 15, 68],
    ['demo-cb-l', 'Yanis Démo', 84, 'CB', 'club', 800, 38.5, 68],
    ['demo-cb-r', 'Camille Exemple', 83, 'CB', 'club', 800, 61.5, 68],
    ['demo-rb', 'Robin Test', 82, 'RB', 'club', 800, 85, 68],
    ['demo-gk', 'Lou Fictive', 83, 'GK', 'club', 400, 50, 89.5],
];
const placements: PitchPlacement[] = setup.map(
    ([id, name, rating, position, origin, value, x, y]) => ({
        player: { id, name, rating, position, origin, value },
        x,
        y,
    }),
);
const players = placements.map(({ player }) => player);
const purchases = players.filter(({ origin }) => origin === 'purchase');
const purchaseCost = purchases.reduce((total, { value }) => total + value, 0);
const sacrificeValue = players
    .filter(({ origin }) => origin === 'club')
    .reduce((total, { value }) => total + value, 0);
const numbers = new Intl.NumberFormat('fr-FR');
const assets = [
    ['Fond anthracite', charcoal, 'charcoal-surface.png'],
    ['Texture du terrain', grass, 'pitch-grass.png'],
    ['Carte dorée', gold, 'card-gold-sketch.svg'],
    ['Silhouette générique', portrait, 'player-silhouette.svg'],
    ['Marque SBC Vision', mark, 'brand-mark.svg'],
    ['Lignes du terrain', lines, 'pitch-lines.svg'],
    ['Forme de carte', mask, 'card-mask.svg'],
];

function KitPreview() {
    const [selectedId, setSelectedId] = useState('demo-cm');
    const [showPurchases, setShowPurchases] = useState(false);
    const [compact, setCompact] = useState(false);
    const selected = players.find(({ id }) => id === selectedId)!;
    const popup = new URLSearchParams(location.search).get('view') === 'popup';
    return (
        <main className={`design-preview ${popup ? 'design-popup' : ''}`}>
            {!popup && (
                <header className="design-preview-header">
                    <div>
                        <p className="design-kicker">SBC VISION / DIRECTION A1</p>
                        <h1>Le kit Stade.</h1>
                        <p>Textures, cartes et éléments graphiques assemblés au format du popup.</p>
                    </div>
                    <a href="./index.html">Retour à l’application ↗</a>
                </header>
            )}
            <div className="design-preview-layout">
                <section className="design-preview-stage" aria-label="Aperçu A1 — Stade">
                    {!popup && (
                        <div className="design-preview-controls">
                            <span>Format du popup</span>
                            <button
                                type="button"
                                aria-pressed={!compact}
                                onClick={() => setCompact(false)}
                            >
                                440 px
                            </button>
                            <button
                                type="button"
                                aria-pressed={compact}
                                onClick={() => setCompact(true)}
                            >
                                360 px
                            </button>
                            <a href="./design-assets.html?view=popup">Isoler ↗</a>
                        </div>
                    )}
                    <div className="design-preview-frame" style={{ maxWidth: compact ? 360 : 440 }}>
                        <article
                            className="stadium-kit"
                            aria-label="Maquette A1 avec des données fictives"
                        >
                            <header className="stadium-header">
                                <StadiumBrand />
                                <a
                                    className="stadium-expand"
                                    href="./index.html"
                                    aria-label="Ouvrir l’application"
                                >
                                    <StadiumIcon name="expand" />
                                </a>
                            </header>
                            <nav className="stadium-tabs" aria-label="Navigation de la maquette">
                                <a href="./index.html">Analyser</a>
                                <span aria-current="page">Équipe</span>
                                <a href="./index.html#connection-title">Réglages</a>
                            </nav>
                            <div className="stadium-content">
                                <div className="stadium-title-row">
                                    <h1>ÉQUIPE PROPOSÉE</h1>
                                    <span className="stadium-demo-label">Exemple fictif</span>
                                </div>
                                <StadiumPitch
                                    placements={placements}
                                    formation="4-3-3"
                                    selectedId={selectedId}
                                    onSelect={setSelectedId}
                                />
                                <div className="stadium-selected" aria-live="polite">
                                    <img src={portrait} alt="" />
                                    <strong>
                                        {selected.rating} · {selected.name} · {selected.position}
                                    </strong>
                                    <span
                                        className={`stadium-origin ${selected.origin === 'purchase' ? 'stadium-origin-purchase' : ''}`}
                                    >
                                        {selected.origin === 'club' ? 'Club' : 'Achat'}
                                    </span>
                                </div>
                                <div className="stadium-costs" aria-label="Coûts fictifs">
                                    <div>
                                        <span>Achats</span>
                                        <strong>{numbers.format(purchaseCost)}</strong>
                                    </div>
                                    <div>
                                        <span>Valeur club</span>
                                        <strong>{numbers.format(sacrificeValue)}</strong>
                                    </div>
                                    <div className="stadium-total">
                                        <span>Total</span>
                                        <strong>
                                            {numbers.format(purchaseCost + sacrificeValue)}
                                        </strong>
                                    </div>
                                </div>
                                <div className="stadium-budget-line">
                                    <span className="stadium-budget">Budget achats : 5 000</span>
                                    <span className="stadium-purchases-caption">
                                        <StadiumIcon name="bag" />
                                        Achats : {purchases.length} joueurs
                                    </span>
                                </div>
                                <div className="stadium-action-row">
                                    <button
                                        className="stadium-cta"
                                        type="button"
                                        aria-expanded={showPurchases}
                                        aria-controls="preview-purchases"
                                        onClick={() => setShowPurchases((value) => !value)}
                                    >
                                        {showPurchases ? 'Masquer les achats' : 'Voir les achats'}
                                    </button>
                                </div>
                                <section
                                    className="stadium-purchases"
                                    id="preview-purchases"
                                    aria-label="Achats de l’exemple"
                                    hidden={!showPurchases}
                                >
                                    <h2>ACHATS DE L’EXEMPLE</h2>
                                    <ul>
                                        {purchases.map((player) => (
                                            <li key={player.id}>
                                                <span>
                                                    {player.name}
                                                    <small>
                                                        {player.rating} · {player.position} · Carte
                                                        fictive
                                                    </small>
                                                </span>
                                                <strong>
                                                    {numbers.format(player.value)} crédits
                                                </strong>
                                            </li>
                                        ))}
                                    </ul>
                                </section>
                            </div>
                        </article>
                    </div>
                    {!popup && (
                        <p className="design-preview-caption">
                            Sélectionne une carte ou ouvre les achats pour vérifier les détails. Cet
                            aperçu ne contacte aucune API.
                        </p>
                    )}
                </section>
                {!popup && (
                    <aside className="design-assets-catalogue" aria-labelledby="catalogue-title">
                        <p className="design-kicker">ASSETS SÉPARÉS</p>
                        <h2 id="catalogue-title">Les pièces du rendu.</h2>
                        <p>
                            Les matières sont des images. Les textes, traits du terrain et
                            interactions restent indépendants.
                        </p>
                        <div className="design-assets-grid">
                            {assets.map(([name, url, filename]) => (
                                <a
                                    className="design-asset"
                                    key={filename}
                                    href={url}
                                    download={filename}
                                >
                                    <div className="design-asset-image">
                                        <img src={url} alt={name} />
                                    </div>
                                    <strong>{name}</strong>
                                    <span>{filename} ↓</span>
                                </a>
                            ))}
                        </div>
                        <div className="design-font-sample">
                            <span>BARLOW CONDENSED</span>
                            <strong>LE JEU DANS LES DÉTAILS.</strong>
                            <p>Polices locales · Version droite et italique</p>
                        </div>
                    </aside>
                )}
            </div>
        </main>
    );
}

createRoot(document.getElementById('design-root')!).render(
    <StrictMode>
        <KitPreview />
    </StrictMode>,
);
