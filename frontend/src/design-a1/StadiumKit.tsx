import type { CSSProperties } from 'react';
import goldCard from './assets/card-gold-sketch.svg';
import silhouette from './assets/player-silhouette.svg';
import pitchLines from './assets/pitch-lines.svg';
import brandMark from './assets/brand-mark.svg';
import './stadium-kit.css';

export type StadiumPlayer = {
    id: string;
    name: string;
    rating: number;
    position: string;
    origin: 'club' | 'purchase';
    value: number;
};
export type PitchPlacement = { player: StadiumPlayer; x: number; y: number };

export function StadiumBrand() {
    return (
        <span className="stadium-brand">
            <img src={brandMark} alt="" width="150" height="60" />
            <span>SBC Vision</span>
        </span>
    );
}

export function StadiumIcon({
    name,
}: {
    name: 'bag' | 'expand' | 'close' | 'scan' | 'arrow' | 'image' | 'server' | 'lock';
}) {
    return (
        <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            aria-hidden="true"
        >
            {name === 'bag' && (
                <>
                    <path d="M5 7h14l1 14H4L5 7Z" />
                    <path d="M9 9V5a3 3 0 0 1 6 0v4" />
                </>
            )}
            {name === 'expand' && <path d="M14 4h6v6m0-6L10 14m-1-9H4v15h15v-5" />}
            {name === 'close' && <path d="m5 5 14 14M19 5 5 19" />}
            {name === 'scan' && <path d="M8 3H3v5m13-5h5v5m0 8v5h-5M3 16v5h5M7 12h10" />}
            {name === 'arrow' && <path d="m9 5 7 7-7 7" />}
            {name === 'image' && (
                <>
                    <rect x="3" y="3" width="18" height="18" rx="1" />
                    <circle cx="8" cy="8" r="1.5" />
                    <path d="m3 17 6-6 4 4 3-3 5 5" />
                </>
            )}
            {name === 'server' && (
                <>
                    <rect x="3" y="3" width="18" height="7" rx="1" />
                    <rect x="3" y="14" width="18" height="7" rx="1" />
                    <path d="M7 6h1m-1 11h1m4-11h5m-5 11h5" />
                </>
            )}
            {name === 'lock' && (
                <>
                    <rect x="5" y="10" width="14" height="11" rx="1" />
                    <path d="M8 10V6a4 4 0 0 1 8 0v4m-4 4v3" />
                </>
            )}
        </svg>
    );
}

export function StadiumCard({
    player,
    selected = false,
    onSelect,
}: {
    player: StadiumPlayer;
    selected?: boolean;
    onSelect: () => void;
}) {
    return (
        <button
            type="button"
            className="stadium-card"
            aria-label={`${player.name}, ${player.rating}, ${player.position}, ${player.origin === 'club' ? 'Club' : 'Achat'}`}
            aria-pressed={selected}
            onClick={onSelect}
        >
            <span className="stadium-card-outline" />
            <StadiumCardFace player={player} />
        </button>
    );
}

// Illustration seule pour les achats ; elle ne crée pas de faux bouton.
export function StadiumCardFace({
    player,
}: {
    player: Pick<StadiumPlayer, 'rating' | 'position' | 'origin'>;
}) {
    return (
        <>
            <img className="stadium-card-gold" src={goldCard} alt="" draggable="false" />
            <img className="stadium-card-portrait" src={silhouette} alt="" draggable="false" />
            <strong className="stadium-card-rating">{player.rating}</strong>
            <span className="stadium-card-position">{player.position}</span>
            {player.origin === 'purchase' && (
                <span className="stadium-card-purchase">
                    <StadiumIcon name="bag" />
                </span>
            )}
        </>
    );
}

// Le kit affiche les coordonnées reçues. Il ne déduit ni formation ni sélection métier.
export function StadiumPitch({
    placements,
    formation,
    selectedId,
    onSelect,
}: {
    placements: PitchPlacement[];
    formation: string;
    selectedId: string;
    onSelect: (id: string) => void;
}) {
    const fullSquad = placements.length === 11;
    // Relief du croquis uniquement ; les coordonnées du rapport restent intactes.
    const drawing = placements.map(({ player, x, y }) => {
        const rowSize = placements.filter((item) => item.y === y).length;
        const lift =
            fullSquad && rowSize > 1
                ? Math.max(0, 1 - Math.abs(x - 50) / 35) * (y >= 60 ? 3.5 : 2)
                : 0;
        return { player, x, y: y - lift };
    });
    return (
        <section
            className="stadium-pitch"
            aria-label={`Composition ${formation}`}
            data-full-squad={fullSquad}
            data-dense={placements.some(
                ({ y }) => placements.filter((item) => item.y === y).length >= 5,
            )}
        >
            <div className="stadium-grass" />
            <img className="stadium-pitch-lines" src={pitchLines} alt="" />
            <span className="stadium-formation">{formation}</span>
            {drawing.map(({ player, x, y }) => (
                <div
                    className="stadium-placement"
                    key={player.id}
                    style={
                        {
                            '--player-x': `${x}%`,
                            '--player-y': `${y}%`,
                        } as CSSProperties
                    }
                >
                    <StadiumCard
                        player={player}
                        selected={selectedId === player.id}
                        onSelect={() => onSelect(player.id)}
                    />
                </div>
            ))}
        </section>
    );
}
