import { FormEvent, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowUpRight } from 'lucide-react'

import { setAccessToken } from '@/services/api'
import { cmsService } from '@/services/cms'

export function LoginPage() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setLoading(true)
    setError('')
    try {
      const session = await cmsService.login(email, password)
      setAccessToken(session.access_token)
      navigate('/studio')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to sign in.')
    } finally {
      setLoading(false)
    }
  }

  return <section className="auth-page"><p className="eyebrow"><span /> NewsForge Studio</p><h1>Make the next story matter.</h1><p>Sign in to write, review and publish with your newsroom.</p><form onSubmit={submit} className="auth-form"><label>Email<input value={email} onChange={event => setEmail(event.target.value)} type="email" required autoComplete="email" /></label><label>Password<input value={password} onChange={event => setPassword(event.target.value)} type="password" required autoComplete="current-password" /></label>{error && <p className="form-error">{error}</p>}<button className="read-button" disabled={loading}>{loading ? 'Signing in…' : <>Sign in <ArrowUpRight size={18}/></>}</button></form><Link to="/" className="back-link">Return to NewsForge</Link></section>
}
