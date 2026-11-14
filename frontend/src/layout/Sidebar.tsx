import dotActive from '../assets/v2/dot-active.svg'
import gear from '../assets/v2/icon-gear.svg'
import trophy from '../assets/v2/icon-trophy.svg'
import logo from '../assets/v2/logo-reversed.svg'
import navGrid from '../assets/v2/nav-grid.svg'
import navHome from '../assets/v2/nav-home.svg'
import navLeaf from '../assets/v2/nav-leaf.svg'
import navShield from '../assets/v2/nav-shield.svg'
import { Icon } from '../components/ui'

export type View = 'overview' | 'rotation' | 'journey' | 'evidence'

const NAV: { view: View; label: string; icon: string }[] = [
  { view: 'overview', label: 'Overview', icon: navHome },
  { view: 'rotation', label: 'Rotation planner', icon: navLeaf },
  { view: 'journey', label: 'Data Journey', icon: navGrid },
  { view: 'evidence', label: 'Evidence & validation', icon: navShield },
]

/** Sidebar (Figma node 25:50). */
export function Sidebar({ view, onNavigate }: { view: View; onNavigate: (view: View) => void }) {
  return (
    <aside className="sidebar">
      <div className="sidebar__brand">
        <img src={logo} width={44} height={34} alt="" />
        <div>
          <strong>FTM</strong>
          <span>Farm Time Machine</span>
        </div>
      </div>
      <p className="sidebar__label">WORKSPACE</p>
      <nav aria-label="Main" className="sidebar__nav">
        {NAV.map((item) => (
          <button
            key={item.view}
            type="button"
            className="sidebar__item"
            aria-current={view === item.view ? 'page' : undefined}
            onClick={() => onNavigate(item.view)}
          >
            <Icon src={item.icon} size={20} />
            <span>{item.label}</span>
            {view === item.view && <img src={dotActive} alt="" />}
          </button>
        ))}
      </nav>
      <div className="spacer" />
      <div className="sidebar__challenge">
        <span className="tile">
          <Icon src={trophy} size={16} />
        </span>
        <div>
          <strong>NASA Space Apps 2026</strong>
          <span>Challenge submission</span>
        </div>
      </div>
      <div className="sidebar__divider" />
      <div className="sidebar__user">
        <span className="tile sidebar__avatar" aria-hidden="true">
          S
        </span>
        <div>
          <strong>Shakil</strong>
          <span>Farm planner</span>
        </div>
        <Icon src={gear} size={18} />
      </div>
    </aside>
  )
}
