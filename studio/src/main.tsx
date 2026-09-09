import { createRoot } from 'react-dom/client'
import { StudioApp } from './app/StudioApp'
import './styles.css'
import './AppShell.css'
import './StudioFixes.css'

createRoot(document.getElementById('root')!).render(<StudioApp/>)
