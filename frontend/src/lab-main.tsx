import { createRoot } from 'react-dom/client';
import ControllerLab from './ControllerLab';
import './style.css';

document.documentElement.classList.add('controller-lab');
createRoot(document.getElementById('root')!).render(<ControllerLab />);
