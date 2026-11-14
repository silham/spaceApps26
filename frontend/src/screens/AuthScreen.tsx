import { useEffect, useRef, useState, type FormEvent } from 'react'
import { api } from '../api/client'
import clockIcon from '../assets/v2/icon-clock.svg'
import dropIcon from '../assets/v2/icon-drop-20.svg'
import leafIcon from '../assets/v2/icon-leaf-20.svg'
import trophy from '../assets/v2/icon-trophy.svg'
import logo from '../assets/v2/logo-reversed.svg'
import { Icon } from '../components/ui'
import type { User } from '../types/contracts'

type Mode = 'sign-in' | 'register'

const FEATURES = [
  { icon: clockIcon, title: 'Replay past seasons', text: "Run a rotation through past years of weather at your field's location." },
  { icon: dropIcon, title: 'Compare water use', text: 'See irrigation need and water-stress days side by side.' },
  { icon: leafIcon, title: 'Protect the soil', text: 'Spot possible low-cover periods, with the uncertainty shown.' },
]

/**
 * Sign in / create account. Shown instead of the workspace whenever there is no session (D14). No Figma frame:
 * built from the frame's tokens, the sidebar's forest brand panel, `.card`, `.segmented` and `.btn`.
 */
export function AuthScreen({ onSignedIn, notice }: { onSignedIn: (user: User) => void; notice?: string }) {
  const [mode, setMode] = useState<Mode>('sign-in')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const heading = useRef<HTMLHeadingElement>(null)
  const switched = useRef(false)
  const register = mode === 'register'

  // After switching tabs, move focus to the new heading for screen-reader users (not on first load).
  useEffect(() => {
    if (switched.current) heading.current?.focus({ preventScroll: true })
  }, [mode])

  const switchTo = (next: Mode) => {
    switched.current = true
    setMode(next)
    setError('')
    setShowPassword(false)
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    const field = (name: string) => String(data.get(name) ?? '')
    if (register && field('password') !== field('confirm_password')) {
      setError('The two passwords do not match.')
      return
    }
    setBusy(true)
    setError('')
    try {
      const credentials = { username: field('username'), password: field('password') }
      onSignedIn(
        register
          ? await api.register({ ...credentials, display_name: field('display_name') })
          : await api.login(credentials),
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong. Try again.')
      setBusy(false)
    }
  }

  return (
    <div className="auth">
      <aside className="auth__brand">
        <div className="auth__logo">
          <img src={logo} width={44} height={34} alt="" />
          <div>
            <strong>FTM</strong>
            <span>Farm Time Machine</span>
          </div>
        </div>
        <div className="auth__pitch">
          <h1>Rehearse your rotation before you plant.</h1>
          <p>Compare your current practice with alternatives on the same historical weather, and see the trade-offs first.</p>
        </div>
        <ul className="auth__features">
          {FEATURES.map((f) => (
            <li key={f.title}>
              <span className="tile auth__feature-icon">
                <Icon src={f.icon} size={20} />
              </span>
              <div>
                <strong>{f.title}</strong>
                <span>{f.text}</span>
              </div>
            </li>
          ))}
        </ul>
        <div className="auth__challenge">
          <span className="auth__challenge-icon">
            <Icon src={trophy} size={16} />
          </span>
          <p>
            <strong>NASA Space Apps 2026</strong> · Challenge submission
          </p>
        </div>
      </aside>

      <main className="auth__panel" id="main">
        <div className="card auth__card">
          <div className="segmented auth__tabs" role="radiogroup" aria-label="Account">
            <button type="button" role="radio" aria-checked={!register} onClick={() => switchTo('sign-in')}>
              Sign in
            </button>
            <button type="button" role="radio" aria-checked={register} onClick={() => switchTo('register')}>
              Create account
            </button>
          </div>

          <div className="auth__heading">
            <h2 ref={heading} tabIndex={-1}>
              {register ? 'Create your account' : 'Welcome back'}
            </h2>
            <p>
              {register
                ? 'Your farms, comparisons and decision cards stay private to your account.'
                : 'Sign in to open your farms and saved decisions.'}
            </p>
          </div>

          {notice && !error && (
            <div className="auth__notice" role="status">
              {notice}
            </div>
          )}
          {error && (
            <div className="auth__error" role="alert">
              {error}
            </div>
          )}

          <form className="auth__form" onSubmit={submit} key={mode}>
            {register && (
              <label className="auth__field">
                <span>Your name</span>
                <input name="display_name" autoComplete="name" required maxLength={100} placeholder="e.g. Sam Rivera" />
              </label>
            )}
            <label className="auth__field">
              <span>Username</span>
              <input
                name="username"
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                required
                minLength={3}
                maxLength={64}
                pattern="[a-zA-Z0-9_.\-]+"
                aria-describedby={register ? 'username-hint' : undefined}
              />
              {register && (
                <small id="username-hint">3–64 letters, numbers, dots, underscores or hyphens.</small>
              )}
            </label>
            <div className="auth__field">
              <span className="auth__label-row">
                <label htmlFor="auth-password">Password</label>
                <button
                  type="button"
                  className="link"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? 'Hide' : 'Show'}
                </button>
              </span>
              <input
                id="auth-password"
                name="password"
                type={showPassword ? 'text' : 'password'}
                autoComplete={register ? 'new-password' : 'current-password'}
                required
                minLength={register ? 15 : 1}
                maxLength={128}
                aria-describedby={register ? 'password-hint' : undefined}
              />
              {register && <small id="password-hint">At least 15 characters. A short phrase is easy to remember.</small>}
            </div>
            {register && (
              <label className="auth__field">
                <span>Confirm password</span>
                <input
                  name="confirm_password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="new-password"
                  required
                  minLength={15}
                  maxLength={128}
                />
              </label>
            )}
            <button className="btn btn--primary auth__submit" disabled={busy}>
              {busy ? (register ? 'Creating account…' : 'Signing in…') : register ? 'Create account' : 'Sign in'}
            </button>
          </form>

          <p className="auth__switch">
            {register ? 'Already have an account?' : 'New to Farm Time Machine?'}{' '}
            <button type="button" className="link" onClick={() => switchTo(register ? 'sign-in' : 'register')}>
              {register ? 'Sign in' : 'Create an account'}
            </button>
          </p>
        </div>
      </main>
    </div>
  )
}
