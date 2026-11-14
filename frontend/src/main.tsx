import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import { isExtension } from './lib/platform';
import './style.css';
import './design-a1/application.css';

// Le popup Chrome a une largeur fixe ; l'onglet de travail reste responsive.
if (isExtension() && new URL(location.href).searchParams.get('view') === 'popup') {
    document.documentElement.classList.add('popup');
}

createRoot(document.getElementById('root')!).render(
    <StrictMode>
        <App />
    </StrictMode>,
);
