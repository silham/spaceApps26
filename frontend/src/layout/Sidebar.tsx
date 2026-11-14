import brandLeaf from '../assets/brand-leaf.svg'
import navGrid from '../assets/nav-grid.svg'
import navHome from '../assets/nav-home.svg'
import navInfo from '../assets/nav-info.svg'
import navLeaf from '../assets/nav-leaf.svg'
import { ctl } from '../components/ctl'

export type View = 'overview' | 'rotation' | 'journey' | 'evidence'

const NAV: { view: View; label: string; icon: string }[] = [
  { view: 'overview', label: 'Overview', icon: navHome },
  { view: 'rotation', label: 'Rotation planner', icon: navLeaf },
  { view: 'journey', label: 'Data Journey', icon: navGrid },
  { view: 'evidence', label: 'Evidence & validation', icon: navInfo },
]

export function Sidebar({ view, onNavigate }: { view: View; onNavigate: (view: View) => void }) {
  return (
    <aside className="sidebar">
      <div className="sidebar__brand">
        <img src={brandLeaf} width={40} height={40} alt="" />
        <span>Farm Time Machine</span>
      </div>
      <nav aria-label="Main" className="sidebar__nav">
        {NAV.map((item) => (
          <button
            key={item.view}
            type="button"
            className="sidebar__item"
            aria-current={view === item.view ? 'page' : undefined}
            onClick={() => onNavigate(item.view)}
          >
            <img src={item.icon} width={20} height={20} alt="" />
            <span>{item.label}</span>
          </button>
        ))}
      </nav>
      <div className="sidebar__spacer" />
      <span className={ctl('outline', 'sidebar__event')}>NASA Space Apps 2026</span>
      <p className="sidebar__caption">Challenge submission</p>
      <div className="sidebar__divider" />
      <p className="sidebar__user">
        <span aria-hidden="true">♙ </span> Shakil <span aria-hidden="true">⚙</span>
      </p>
    </aside>
  )
}
