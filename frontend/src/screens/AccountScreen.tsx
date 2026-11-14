import { useState, type FormEvent } from 'react'
import { api } from '../api/client'
import type { User } from '../types/contracts'

type Message = { tone: 'ok' | 'error'; text: string } | null

/** Signed-in account settings: profile, password, sign out. No Figma frame: `.page-card` and `.form` patterns. */
export function AccountScreen({ user, onUserChange }: { user: User; onUserChange: (user: User | null) => void }) {
  const [busy, setBusy] = useState<'profile' | 'password' | 'logout' | null>(null)
  const [profileMsg, setProfileMsg] = useState<Message>(null)
  const [passwordMsg, setPasswordMsg] = useState<Message>(null)
  const [logoutError, setLogoutError] = useState('')

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const name = String(new FormData(event.currentTarget).get('display_name') ?? '')
    setBusy('profile')
    setProfileMsg(null)
    try {
      onUserChange(await api.updateProfile({ display_name: name }))
      setProfileMsg({ tone: 'ok', text: 'Profile saved.' })
    } catch (err) {
      setProfileMsg({ tone: 'error', text: err instanceof Error ? err.message : 'Could not save your profile.' })
    } finally {
      setBusy(null)
    }
  }

  async function changePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const data = new FormData(form)
    if (data.get('new_password') !== data.get('confirm_password')) {
      setPasswordMsg({ tone: 'error', text: 'The two new passwords do not match.' })
      return
    }
    setBusy('password')
    setPasswordMsg(null)
    try {
      await api.changePassword({
        current_password: String(data.get('current_password')),
        new_password: String(data.get('new_password')),
      })
      form.reset()
      setPasswordMsg({ tone: 'ok', text: 'Password changed. Your other sessions have been signed out.' })
    } catch (err) {
      setPasswordMsg({ tone: 'error', text: err instanceof Error ? err.message : 'Could not change your password.' })
    } finally {
      setBusy(null)
    }
  }

  async function logout() {
    setBusy('logout')
    setLogoutError('')
    try {
      await api.logout()
      onUserChange(null)
    } catch (err) {
      setLogoutError(err instanceof Error ? err.message : 'Could not sign out. Try again.')
      setBusy(null)
    }
  }

  const feedback = (msg: Message) =>
    msg && (
      <p className={msg.tone === 'ok' ? 'account__ok' : 'run-error'} role={msg.tone === 'ok' ? 'status' : 'alert'}>
        {msg.text}
      </p>
    )

  return (
    <>
      <div className="page-head">
        <h1 className="page-title" tabIndex={-1}>
          Your account
        </h1>
        <p className="muted">Signed in as {user.username}</p>
      </div>
      <div className="account-grid">
        <section className="card page-card" aria-labelledby="profile-h">
          <div className="card-title card-title--small">
            <h2 id="profile-h">Profile</h2>
            <p>The name shown in the sidebar and on your decision cards.</p>
          </div>
          <form className="form" onSubmit={saveProfile}>
            <label>
              Your name
              <input name="display_name" autoComplete="name" defaultValue={user.display_name} required maxLength={100} />
            </label>
            <p className="small muted">
              Username <strong className="account__username">{user.username}</strong> (cannot be changed)
            </p>
            {feedback(profileMsg)}
            <div className="form__actions">
              <button className="btn btn--primary" disabled={busy !== null}>
                {busy === 'profile' ? 'Saving…' : 'Save profile'}
              </button>
            </div>
          </form>
        </section>

        <section className="card page-card" aria-labelledby="password-h">
          <div className="card-title card-title--small">
            <h2 id="password-h">Change password</h2>
            <p>At least 15 characters. Changing it signs out your other sessions.</p>
          </div>
          <form className="form" onSubmit={changePassword}>
            <label>
              Current password
              <input name="current_password" type="password" autoComplete="current-password" required maxLength={128} />
            </label>
            <label>
              New password
              <input name="new_password" type="password" autoComplete="new-password" required minLength={15} maxLength={128} />
            </label>
            <label>
              Confirm new password
              <input name="confirm_password" type="password" autoComplete="new-password" required minLength={15} maxLength={128} />
            </label>
            {feedback(passwordMsg)}
            <div className="form__actions">
              <button className="btn btn--secondary" disabled={busy !== null}>
                {busy === 'password' ? 'Changing…' : 'Change password'}
              </button>
            </div>
          </form>
        </section>
      </div>

      <section className="card page-card account-signout" aria-labelledby="signout-h">
        <div className="card-title card-title--small">
          <h2 id="signout-h">Sign out</h2>
          <p>End this session on this browser.</p>
        </div>
        {logoutError && (
          <p className="run-error" role="alert">
            {logoutError}
          </p>
        )}
        <button className="btn btn--secondary" disabled={busy !== null} onClick={() => void logout()}>
          {busy === 'logout' ? 'Signing out…' : 'Sign out'}
        </button>
      </section>
    </>
  )
}
