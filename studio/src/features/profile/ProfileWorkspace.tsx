import { FormEvent, useState } from 'react'
import { api } from '../../shared/api/client'
import type { User } from '../../types'

export function ProfileWorkspace({ user, onUpdated }: { user: User; onUpdated: (user: User) => void }) {
  const [name, setName] = useState(user.display_name), [email, setEmail] = useState(user.email), [password, setPassword] = useState(''), [notice, setNotice] = useState('')
  const save = async (event: FormEvent) => { event.preventDefault(); try { const next = await api.updateProfile({ display_name: name, email, ...(password ? { password } : {}) }); onUpdated(next); setPassword(''); setNotice('Profile saved.') } catch (error) { setNotice(error instanceof Error ? error.message : 'Could not save profile.') } }
  return <section className="settings-workspace"><p className="eyebrow">PROFILE</p><h1>Your profile</h1><form className="profile-form" onSubmit={save}><label>Name<input value={name} onChange={event => setName(event.target.value)} required/></label><label>Email<input value={email} onChange={event => setEmail(event.target.value)} type="email" required/></label><label>New password<input value={password} onChange={event => setPassword(event.target.value)} type="password" minLength={10}/></label><span>{notice}</span><button>Save changes</button></form></section>
}
