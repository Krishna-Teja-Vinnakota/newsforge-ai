import { FormEvent, useEffect, useState } from 'react'
import { api } from '../../shared/api/client'
import { DialogForm, StudioDialog } from '../../StudioDialog'
import type { Role, User } from '../../types'
import './UserManagement.css'

type EditorState = 'create' | 'edit' | 'deactivate' | null
const roles: Role[] = ['admin', 'editor']
const empty = { display_name: '', email: '', password: '', role: 'editor' as Role, is_active: true }

export function UserManagementWorkspace({ currentUser }: { currentUser: User }) {
  const [users, setUsers] = useState<User[]>([])
  const [dialog, setDialog] = useState<EditorState>(null)
  const [selected, setSelected] = useState<User | null>(null)
  const [form, setForm] = useState(empty)
  const [notice, setNotice] = useState('')
  const load = () => {
    void api
      .users()
      .then(setUsers)
      .catch((error) => setNotice(error.message))
  }
  useEffect(load, [])
  const openCreate = () => {
    setSelected(null)
    setForm(empty)
    setDialog('create')
  }
  const openEdit = (user: User) => {
    setSelected(user)
    setForm({
      display_name: user.display_name,
      email: user.email,
      password: '',
      role: user.role,
      is_active: user.is_active,
    })
    setDialog('edit')
  }
  const save = async (event: FormEvent) => {
    event.preventDefault()
    try {
      if (dialog === 'create')
        await api.createUser({
          email: form.email,
          password: form.password,
          display_name: form.display_name,
          role: form.role,
        })
      if (dialog === 'edit' && selected)
        await api.updateUser(selected.id, {
          display_name: form.display_name,
          email: form.email,
          role: form.role,
          is_active: form.is_active,
          ...(form.password ? { password: form.password } : {}),
        })
      setNotice(dialog === 'create' ? 'User created.' : 'User updated.')
      setDialog(null)
      load()
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Unable to save user.')
    }
  }
  const deactivate = async () => {
    if (!selected) return
    try {
      await api.deleteUser(selected.id)
      setDialog(null)
      setNotice('User deactivated.')
      load()
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Unable to deactivate user.')
    }
  }
  return (
    <section className="user-management">
      <header className="user-management-header">
        <div>
          <p className="eyebrow">ADMINISTRATION</p>
          <h1>User management</h1>
          <p>Create newsroom accounts and manage access levels.</p>
        </div>
        <button className="user-primary" onClick={openCreate}>
          + Add user
        </button>
      </header>
      {notice && <p className="notice">{notice}</p>}
      <section className="user-table">
        <header>
          <span>User</span>
          <span>Role</span>
          <span>Status</span>
          <span />
        </header>
        {users.map((user) => (
          <article key={user.id}>
            <div className="user-identity">
              <span>{user.display_name.slice(0, 1).toUpperCase()}</span>
              <div>
                <b>
                  {user.display_name}
                  {user.id === currentUser.id && ' (you)'}
                </b>
                <small>{user.email}</small>
              </div>
            </div>
            <span className="user-role">{user.role}</span>
            <span className={user.is_active ? 'user-status active' : 'user-status'}>
              {user.is_active ? 'Active' : 'Inactive'}
            </span>
            <div className="user-actions">
              <button onClick={() => openEdit(user)}>Edit</button>
              {user.id !== currentUser.id && user.is_active && (
                <button
                  className="danger"
                  onClick={() => {
                    setSelected(user)
                    setDialog('deactivate')
                  }}
                >
                  Deactivate
                </button>
              )}
            </div>
          </article>
        ))}
      </section>
      {(dialog === 'create' || dialog === 'edit') && (
        <StudioDialog
          title={dialog === 'create' ? 'Create user' : `Edit ${selected?.display_name}`}
          onClose={() => setDialog(null)}
        >
          <DialogForm onSubmit={save}>
            <label>
              Name
              <input
                autoFocus
                value={form.display_name}
                onChange={(event) => setForm({ ...form, display_name: event.target.value })}
                required
              />
            </label>
            <label>
              Email
              <input
                type="email"
                value={form.email}
                onChange={(event) => setForm({ ...form, email: event.target.value })}
                required
              />
            </label>
            <label>
              {dialog === 'create' ? 'Temporary password' : 'New password (leave empty to keep current)'}
              <input
                type="password"
                value={form.password}
                onChange={(event) => setForm({ ...form, password: event.target.value })}
                minLength={10}
                required={dialog === 'create'}
              />
            </label>
            <label>
              Role
              <select value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value as Role })}>
                {roles.map((role) => (
                  <option key={role} value={role}>
                    {role}
                  </option>
                ))}
              </select>
            </label>
            {dialog === 'edit' && selected?.id !== currentUser.id && (
              <label className="user-active-toggle">
                <input
                  type="checkbox"
                  checked={form.is_active}
                  onChange={(event) => setForm({ ...form, is_active: event.target.checked })}
                />{' '}
                Account is active
              </label>
            )}
            <div className="dialog-actions">
              <button type="button" onClick={() => setDialog(null)}>
                Cancel
              </button>
              <button className="dialog-primary" type="submit">
                {dialog === 'create' ? 'Create user' : 'Save changes'}
              </button>
            </div>
          </DialogForm>
        </StudioDialog>
      )}
      {dialog === 'deactivate' && (
        <StudioDialog title={`Deactivate ${selected?.display_name}?`} onClose={() => setDialog(null)}>
          <DialogForm
            onSubmit={(event) => {
              event.preventDefault()
              void deactivate()
            }}
          >
            <p>The user will no longer be able to sign in. Their existing stories will remain intact.</p>
            <div className="dialog-actions">
              <button type="button" onClick={() => setDialog(null)}>
                Cancel
              </button>
              <button className="dialog-danger" type="submit">
                Deactivate user
              </button>
            </div>
          </DialogForm>
        </StudioDialog>
      )}
    </section>
  )
}
