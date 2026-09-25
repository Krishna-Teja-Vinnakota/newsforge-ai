import { useEffect, useState } from 'react'
import { LogOut, Sparkles, Users } from 'lucide-react'
import { LoginPage } from '../features/auth/LoginPage'
import { AiDesk } from '../features/ai/AiDesk'
import { ProfileWorkspace } from '../features/profile/ProfileWorkspace'
import { StoriesWorkspace } from '../features/stories/StoriesWorkspace'
import { SettingsWorkspace } from '../features/taxonomy/TaxonomyWorkspace'
import { UserManagementWorkspace } from '../features/users/UserManagementWorkspace'
import { api, clearToken, sessionToken } from '../shared/api/client'
import type { User } from '../types'

type View = 'stories' | 'settings' | 'profile' | 'users' | 'ai'
export function StudioApp() {
  const [user, setUser] = useState<User | null>(null),
    [ready, setReady] = useState(false)
  useEffect(() => {
    if (!sessionToken()) {
      setReady(true)
      return
    }
    void api
      .me()
      .then(setUser)
      .catch(clearToken)
      .finally(() => setReady(true))
  }, [])
  if (!ready) return <main className="login-shell">Opening Studio…</main>
  return user ? <StudioShell user={user} onUserUpdated={setUser} /> : <LoginPage onSignedIn={setUser} />
}
function StudioShell({ user, onUserUpdated }: { user: User; onUserUpdated: (user: User) => void }) {
  const [view, setView] = useState<View>('stories'),
    [collapsed, setCollapsed] = useState(false),
    [dark, setDark] = useState(localStorage.getItem('newsforge.studio.theme') === 'dark'),
    [userMenu, setUserMenu] = useState(false),
    [openArticleId, setOpenArticleId] = useState<string | null>(null)
  useEffect(() => {
    document.documentElement.dataset.theme = dark ? 'dark' : 'light'
    localStorage.setItem('newsforge.studio.theme', dark ? 'dark' : 'light')
  }, [dark])
  const signOut = () => {
    clearToken()
    location.reload()
  }
  const openProfile = () => {
    setView('profile')
    setUserMenu(false)
  }
  return (
    <main className={collapsed ? 'studio-app collapsed' : 'studio-app'}>
      <aside className="sidebar">
        <div>
          <a className="brand" href="http://localhost:5173">
            news<span>forge</span>
            <i>.</i>
          </a>
          <button className="collapse-button" onClick={() => setCollapsed(!collapsed)}>
            {collapsed ? '»' : '«'}
          </button>
        </div>
        <nav>
          <button className={view === 'stories' ? 'active' : ''} onClick={() => setView('stories')}>
            <span>▤</span>
            <b>Stories</b>
          </button>
          {(user.role === 'admin' || user.role === 'editor') && (
            <button className={view === 'ai' ? 'active' : ''} onClick={() => setView('ai')}>
              <span className="nav-icon" aria-hidden>
                <Sparkles size={16} strokeWidth={2} />
              </span>
              <b>AI desk</b>
            </button>
          )}
          {user.role === 'admin' && (
            <>
              <button className={view === 'users' ? 'active' : ''} onClick={() => setView('users')}>
                <span className="nav-icon" aria-hidden>
                  <Users size={16} strokeWidth={2} />
                </span>
                <b>Users</b>
              </button>
              <button className={view === 'settings' ? 'active' : ''} onClick={() => setView('settings')}>
                <span>⚙</span>
                <b>Settings</b>
              </button>
            </>
          )}
        </nav>
        <div className="sidebar-user">
          <button className="user-profile-link" onClick={openProfile}>
            <span>{user.display_name.slice(0, 1).toUpperCase()}</span>
            <div>
              <b>{user.display_name}</b>
              <small>{user.role}</small>
            </div>
          </button>
          {userMenu && (
            <div className="user-menu">
              <button onClick={openProfile}>Profile</button>
              <button
                onClick={() => {
                  setDark(!dark)
                  setUserMenu(false)
                }}
              >
                {dark ? 'Light mode' : 'Dark mode'}
              </button>
              <button onClick={signOut}>
                <LogOut size={14} /> Sign out
              </button>
            </div>
          )}
        </div>
        <div className="sidebar-bottom">
          <button onClick={() => setDark(!dark)}>
            <span>{dark ? '☀' : '◐'}</span>
            <b>{dark ? 'Light mode' : 'Dark mode'}</b>
          </button>
          <button onClick={signOut}>
            <span className="nav-icon" aria-hidden>
              <LogOut size={16} strokeWidth={2} />
            </span>
            <b>Sign out</b>
          </button>
        </div>
      </aside>
      <section className="workspace">
        {view === 'stories' && (
          <StoriesWorkspace user={user} openArticleId={openArticleId} onOpenArticleHandled={() => setOpenArticleId(null)} />
        )}{' '}
        {view === 'ai' && (user.role === 'admin' || user.role === 'editor') && (
          <AiDesk
            onDraftCreated={(articleId) => {
              setOpenArticleId(articleId)
              setView('stories')
            }}
          />
        )}{' '}
        {view === 'users' && user.role === 'admin' && <UserManagementWorkspace currentUser={user} />}{' '}
        {view === 'settings' && user.role === 'admin' && <SettingsWorkspace />}{' '}
        {view === 'profile' && <ProfileWorkspace user={user} onUpdated={onUserUpdated} />}
      </section>
    </main>
  )
}
