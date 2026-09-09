import { FormEvent, useState } from 'react'
import { api, saveToken } from '../../shared/api/client'
import type { User } from '../../types'

export function LoginPage({ onSignedIn }: { onSignedIn: (user: User) => void }) {
  const [email, setEmail] = useState('admin@newsforge.dev')
  const [password, setPassword] = useState('NewsForgeAdmin#2026')
  const [error, setError] = useState('')
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    try { const session = await api.login(email, password); saveToken(session.access_token); onSignedIn(session.user) }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to sign in.') }
  }
  return <main className="login-shell"><section className="login-card"><a className="brand" href="http://localhost:5173">news<span>forge</span><i>.</i></a><p className="eyebrow">PRIVATE NEWSROOM</p><h1>Stories start <em>here.</em></h1><form onSubmit={submit}><label>Email<input value={email} onChange={event => setEmail(event.target.value)} type="email" required/></label><label>Password<input value={password} onChange={event => setPassword(event.target.value)} type="password" required/></label>{error && <p className="error">{error}</p>}<button>Open Studio →</button></form></section></main>
}
