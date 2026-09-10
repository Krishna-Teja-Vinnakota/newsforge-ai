import { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Link, useLocation } from 'react-router-dom'
import {
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  Bookmark,
  Cloud,
  CloudRain,
  CloudSun,
  Clock3,
  Droplets,
  Eye,
  Gauge,
  Menu,
  Moon,
  RefreshCw,
  Search,
  Share2,
  Sparkles,
  Sun,
  Sunrise,
  Wind,
  X,
} from 'lucide-react'
import { newsRepository } from './repositories/news-repository'
import type { Story } from './types/news'
import { ApiArticleReader } from './components/news/ApiArticleReader'
import { TrendingRail } from './components/news/TrendingRail'
import { NewsDashboard } from './components/news/NewsDashboard'

import { cacheAge, getWeather, type ForecastPoint, type WeatherLocation, type WeatherSnapshot } from './lib/weather'
import { readSavedLocation, saveLocation, searchLocations, type LocationChoice } from './lib/location'
import './styles.css'

const news = newsRepository.getSnapshot()

function ArticlePage({ onSave, saved, story }: { onSave: () => void; saved: boolean; story?: Story }) {
  const article = story ?? news.hero
  const articleIndex = news.stories.findIndex((item) => item.id === article.id)
  const previousStory = articleIndex > 0 ? news.stories[articleIndex - 1] : undefined
  const nextStory = articleIndex >= 0 ? news.stories[articleIndex + 1] : news.stories[0]
  const [shareLabel, setShareLabel] = useState('Share')
  const share = async () => {
    try {
      if (navigator.share) await navigator.share({ title: article.title, url: window.location.href })
      else await navigator.clipboard.writeText(window.location.href)
      setShareLabel('Link copied')
      window.setTimeout(() => setShareLabel('Share'), 1800)
    } catch {
      /* User cancelled the native share sheet or clipboard access was unavailable. */
    }
  }
  return (
    <section className="article-layout">
      <article className="article-page">
        <a className="back-link" href="/">
          <ArrowLeft size={16} /> Back to latest
        </a>
        <p className="eyebrow article-category">
          <span /> {article.category}
        </p>
        <h1>{article.title}</h1>
        <p className="article-dek">{article.excerpt}</p>
        <div className="article-info">
          <span className="avatar">{news.article.authorInitials}</span>
          <div>
            <b>By {article.author}</b>
            <small>Staff writer · {article.date}</small>
          </div>
          <span className="article-read">
            <Clock3 size={15} />
            {article.readTime}
          </span>
          <button className={'article-save ' + (saved ? 'saved' : '')} onClick={onSave}>
            <Bookmark size={17} fill={saved ? 'currentColor' : 'none'} />
            {saved ? 'Saved' : 'Save'}
          </button>
          <button className="article-save" onClick={() => void share()}>
            <Share2 size={17} />
            {shareLabel}
          </button>
        </div>
        <img className="article-image" src={article.image} alt="Article visual" />
        <div className="article-body">
          <aside>
            <span>IN THIS STORY</span>
            {news.article.toc.map((item) => (
              <a href={'#' + item.id} key={item.id}>
                {item.label}
              </a>
            ))}
          </aside>
          <div className="prose">
            {news.article.body.map((block, index) =>
              block.type === 'heading' ? (
                <h2 id={block.id} key={index}>
                  {block.text}
                </h2>
              ) : block.type === 'quote' ? (
                <blockquote key={index}>“{block.text}”</blockquote>
              ) : (
                <p id={block.id} className={block.type === 'lead' ? 'lead' : ''} key={index}>
                  {block.text}
                </p>
              )
            )}
          </div>
        </div>
        <section className="related">
          <p className="eyebrow">
            <span /> Continue reading
          </p>
          <h2>More in Climate & Science</h2>
          <div className="mini-related">
            {news.stories.slice(0, 2).map((story) => (
              <Link to={`/article?story=${story.id}`} key={story.title}>
                <img src={story.image} alt="" />
                <div>
                  <p>{story.category}</p>
                  <h3>{story.title}</h3>
                  <ArrowUpRight size={18} />
                </div>
              </Link>
            ))}
          </div>
        </section>
        <nav className="article-navigation" aria-label="Article navigation">
          {previousStory ? (
            <Link to={`/article?story=${previousStory.id}`}>
              <ArrowLeft size={16} />
              <span><small>Previous story</small>{previousStory.title}</span>
            </Link>
          ) : <span className="article-navigation-empty" />}
          {nextStory ? (
            <Link className="next" to={`/article?story=${nextStory.id}`}>
              <span><small>Next story</small>{nextStory.title}</span>
              <ArrowRight size={16} />
            </Link>
          ) : <span className="article-navigation-empty" />}
        </nav>
      </article>
      <TrendingRail />
    </section>
  )
}

function CategoryPage() {
  const stories = news.stories
  const headline = news.channel.headline.split(', ')
  return (
    <section className="category-page">
      <div className="category-hero">
        <p className="eyebrow">
          <span /> NewsForge channel
        </p>
        <h1>
          {headline[0]},<br />
          <em>{headline[1]}</em>
        </h1>
        <p>{news.channel.description}</p>
      </div>
      <div className="category-tabs">
        {news.channel.tabs.map((tab, index) =>
          index === 0 ? (
            <Link className="active" to="/technology" key={tab}>
              {tab}
            </Link>
          ) : (
            <a href="#latest" key={tab}>
              {tab}
            </a>
          )
        )}
      </div>
      <div className="category-feature">
        <img src={stories[0].image} alt="Library interior" />
        <div>
          <p className="eyebrow">
            <span /> {news.channel.featureLabel}
          </p>
          <h2>{stories[0].title}</h2>
          <p>{news.channel.featureDescription}</p>
          <Link to={`/article?story=${stories[0].id}`}>
            Read the story <ArrowUpRight size={17} />
          </Link>
        </div>
      </div>
      <div className="channel-head">
        <h2>Latest in technology</h2>
        <span>{news.channel.storyCount}</span>
      </div>
      <div className="channel-grid">
        {stories.slice(1).map((story, i) => (
          <article key={story.title}>
            <img src={story.image} alt="" />
            <p>
              {String(i + 1).padStart(2, '0')} · {story.category}
            </p>
            <h3>{story.title}</h3>
            <small>
              {story.author} · {story.readTime}
            </small>
          </article>
        ))}
      </div>
    </section>
  )
}

function SearchPanel({ close }: { close: () => void }) {
  const [query, setQuery] = useState('')
  const items = [news.hero, ...news.stories].filter(
    (story) =>
      story.title.toLowerCase().includes(query.toLowerCase()) ||
      story.category.toLowerCase().includes(query.toLowerCase())
  )
  return (
    <div className="search-overlay" role="dialog" aria-modal="true" aria-label="Search NewsForge">
      <div className="search-panel">
        <div className="search-input">
          <Search size={19} />
          <input
            autoFocus
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search stories, topics and writers"
            aria-label="Search stories"
          />
          <button onClick={close} aria-label="Close search">
            <X size={19} />
          </button>
        </div>
        <p className="search-label">{query ? 'Matching stories' : 'Explore the latest'}</p>
        <div className="search-results">
          {items.map((story) => (
            <Link to={'id' in story ? `/article?story=${story.id}` : '/article'} key={story.title} onClick={close}>
              <span>{story.category}</span>
              <b>{story.title}</b>
              <ArrowUpRight size={17} />
            </Link>
          ))}
          {items.length === 0 && <p className="no-results">No stories found. Try another phrase.</p>}
        </div>
      </div>
    </div>
  )
}

function WeatherPage() {
  const [weather, setWeather] = useState<WeatherSnapshot | null>(null)
  const [forecast, setForecast] = useState<ForecastPoint[]>([])
  const [isCached, setIsCached] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [location, setLocation] = useState<WeatherLocation | undefined>(() => readSavedLocation())
  const [locationQuery, setLocationQuery] = useState(() => {
    const saved = readSavedLocation()
    return saved ? `${saved.name}${saved.country ? `, ${saved.country}` : ''}` : ''
  })
  const [suggestions, setSuggestions] = useState<LocationChoice[]>([])
  const [searchingLocations, setSearchingLocations] = useState(false)

  const loadWeather = async (force = false, nextLocation = location) => {
    setLoading(true)
    setError('')
    try {
      const result = await getWeather(nextLocation, force)
      setWeather(result.data)
      setForecast(result.forecast)
      setIsCached(result.cached)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Weather is temporarily unavailable.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadWeather()
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(async () => {
      if (locationQuery.trim().length < 3) return setSuggestions([])
      setSearchingLocations(true)
      try {
        setSuggestions(await searchLocations(locationQuery, controller.signal))
      } catch {
        setSuggestions([])
      } finally {
        setSearchingLocations(false)
      }
    }, 350)
    return () => {
      controller.abort()
      window.clearTimeout(timer)
    }
  }, [locationQuery])
  const selectLocation = (choice: LocationChoice) => {
    setLocation(choice)
    saveLocation(choice)
    setLocationQuery(`${choice.name}${choice.country ? `, ${choice.country}` : ''}`)
    setSuggestions([])
    void loadWeather(true, choice)
  }
  const WeatherIcon =
    weather?.condition === 'Rain' || weather?.condition === 'Drizzle' || weather?.condition === 'Thunderstorm'
      ? CloudRain
      : weather?.condition === 'Clear'
        ? Sun
        : weather?.condition === 'Clouds'
          ? Cloud
          : CloudSun

  return (
    <section className="weather-page">
      <div className="weather-heading">
        <div>
          <p className="eyebrow">
            <span /> Local conditions
          </p>
          <h1>
            Weather, <em>now.</em>
          </h1>
          <p>Current conditions for your location, updated thoughtfully.</p>
        </div>
        <button className="weather-refresh" onClick={() => void loadWeather(true)} disabled={loading}>
          <RefreshCw size={16} className={loading ? 'spin' : ''} />
          {loading ? 'Updating' : 'Refresh weather'}
        </button>
      </div>
      <div className="location-picker">
        <Search size={18} />
        <input
          value={locationQuery}
          onChange={(event) => setLocationQuery(event.target.value)}
          placeholder="Search a city or place"
          aria-label="Search a location"
        />
        <span>{searchingLocations ? 'Searching…' : 'Powered by Geoapify'}</span>
        {suggestions.length > 0 && (
          <div className="location-suggestions">
            {suggestions.map((choice) => (
              <button key={`${choice.lat}-${choice.lon}`} onClick={() => selectLocation(choice)}>
                <b>{choice.name}</b>
                <span>{choice.country}</span>
              </button>
            ))}
          </div>
        )}
      </div>
      {loading && !weather && (
        <div className="weather-state">
          <CloudSun size={38} />
          <p>Finding your local forecast…</p>
        </div>
      )}
      {error && (
        <div className="weather-state error">
          <p>{error}</p>
          <p className="weather-help">
            Create a local <code>.env</code> from <code>.env.example</code>, add your free OpenWeatherMap key, then
            restart the dev server.
          </p>
        </div>
      )}
      {weather && (
        <>
          <section className="weather-card">
            <img
              className="weather-gif"
              src="https://cdn.dribbble.com/userupload/25398855/file/original-b39f61791073c4efb3ba40bf4167eb31.gif"
              alt="Animated sun and cloud"
            />
            <div className="weather-main">
              <p className="weather-place">
                {weather.location}, {weather.country}
              </p>
              <div className="weather-temperature">
                <WeatherIcon strokeWidth={1.3} />
                <strong>{weather.temperature}°</strong>
                <span>C</span>
              </div>
              <p className="weather-condition">{weather.description}</p>
              <p className="weather-feels">Feels like {weather.feelsLike}°</p>
            </div>
            <div className="weather-side">
              <div className="weather-updated">
                <span className={isCached ? 'cached-dot' : 'fresh-dot'} />
                {isCached ? 'Saved reading' : 'Live reading'} · {cacheAge(weather.observedAt)}
              </div>
              <div className="sun-times">
                <div>
                  <Sunrise size={20} />
                  <span>
                    Sunrise{' '}
                    <b>
                      {new Date(weather.sunrise * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}
                    </b>
                  </span>
                </div>
                <div>
                  <SunsetIcon />
                  <span>
                    Sunset{' '}
                    <b>
                      {new Date(weather.sunset * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}
                    </b>
                  </span>
                </div>
              </div>
            </div>
          </section>
          <section className="weather-details">
            <div>
              <Droplets />
              <span>Humidity</span>
              <b>{weather.humidity}%</b>
            </div>
            <div>
              <Wind />
              <span>Wind</span>
              <b>{weather.windSpeed} km/h</b>
            </div>
            <div>
              <Eye />
              <span>Visibility</span>
              <b>{weather.visibility ? `${weather.visibility} km` : '—'}</b>
            </div>
            <div>
              <Gauge />
              <span>Pressure</span>
              <b>{weather.pressure} hPa</b>
            </div>
          </section>
          {forecast.length > 0 && (
            <section className="forecast">
              <div>
                <p className="eyebrow">
                  <span /> Ahead
                </p>
                <h2>Five-day outlook</h2>
              </div>
              <div className="forecast-grid">
                {forecast.map((point, index) => (
                  <div key={point.timestamp}>
                    <span>
                      {index === 0
                        ? 'Today'
                        : new Intl.DateTimeFormat(undefined, { weekday: 'short' }).format(point.timestamp * 1000)}
                    </span>
                    <CloudSun />
                    <b>{point.temperature}°</b>
                    <small>{point.condition}</small>
                  </div>
                ))}
              </div>
            </section>
          )}
          <p className="weather-cache-note">
            To respect the free API allowance, this page makes two free-plan requests on first visit (current weather
            and 5-day forecast) and reuses them for one hour. “Refresh weather” always requests new readings.
          </p>
        </>
      )}
    </section>
  )
}

function SunsetIcon() {
  return <Sun size={20} />
}

function TopWeather() {
  const [weather, setWeather] = useState<WeatherSnapshot | null>(null)
  const [location, setLocation] = useState<WeatherLocation | undefined>(() => readSavedLocation())
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState(() => {
    const saved = readSavedLocation()
    return saved ? `${saved.name}${saved.country ? `, ${saved.country}` : ''}` : ''
  })
  const [suggestions, setSuggestions] = useState<LocationChoice[]>([])
  useEffect(() => {
    void getWeather(location)
      .then((result) => setWeather(result.data))
      .catch(() => undefined)
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(async () => {
      if (!open || query.trim().length < 3) return setSuggestions([])
      try {
        setSuggestions(await searchLocations(query, controller.signal))
      } catch {
        setSuggestions([])
      }
    }, 300)
    return () => {
      controller.abort()
      window.clearTimeout(timer)
    }
  }, [open, query])
  const choose = (choice: LocationChoice) => {
    setLocation(choice)
    saveLocation(choice)
    setQuery(`${choice.name}${choice.country ? `, ${choice.country}` : ''}`)
    setSuggestions([])
    setOpen(false)
    void getWeather(choice, true)
      .then((result) => setWeather(result.data))
      .catch(() => undefined)
  }
  return (
    <div className="top-weather">
      <Link to="/weather" className="weather-chip">
        <CloudSun size={14} />
        <span>{weather ? `${Math.round(weather.temperature)}° · ${weather.description}` : 'Weather'}</span>
      </Link>
      <button onClick={() => setOpen(!open)} className="location-chip">
        <span>⌖</span>
        {weather?.location ?? location?.name ?? 'Set location'}
      </button>
      {open && (
        <div className="top-location-popover">
          <div>
            <Search size={14} />
            <input
              autoFocus
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search city"
            />
          </div>
          {suggestions.map((choice) => (
            <button key={`${choice.lat}-${choice.lon}`} onClick={() => choose(choice)}>
              <b>{choice.name}</b>
              <span>{choice.country}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function App() {
  const [dark, setDark] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [saved, setSaved] = useState<string[]>([])
  const [searchOpen, setSearchOpen] = useState(false)
  const [subscribed, setSubscribed] = useState(false)
  const { pathname: route, search } = useLocation()
  const articleId = new URLSearchParams(search).get('story')
  const articleSlug = route.startsWith('/article/') ? decodeURIComponent(route.slice('/article/'.length)) : null
  const selectedStory = newsRepository.getStoryById(articleId)

  useEffect(() => {
    document.documentElement.dataset.theme = dark ? 'dark' : 'light'
  }, [dark])
  const toggleSave = (title: string) =>
    setSaved((items) => (items.includes(title) ? items.filter((item) => item !== title) : [...items, title]))

  return (
    <main>
      <div className="topline">
        <span>Independent journalism for curious minds</span>
        <div>
          <span className="edition">
            {new Intl.DateTimeFormat(undefined, { weekday: 'long', month: 'short', day: 'numeric' }).format(new Date())}
          </span>
          <TopWeather />
        </div>
      </div>
      <header>
        <button className="mobile-menu icon-button" onClick={() => setMenuOpen(!menuOpen)} aria-label="Open navigation">
          {menuOpen ? <X /> : <Menu />}
        </button>
        <Link className="brand" to="/">
          news<span>forge</span>
          <i>.</i>
        </Link>
        <nav className={menuOpen ? 'open' : ''}>
          <Link to="/">Latest news</Link>
          <Link to="/weather">Weather</Link>
        </nav>
        <div className="header-actions">
          <button className="icon-button search" onClick={() => setSearchOpen(true)} aria-label="Search">
            <Search size={19} />
          </button>
          <button className="theme-switch" onClick={() => setDark(!dark)} aria-label="Toggle dark mode">
            {dark ? <Sun size={16} /> : <Moon size={16} />}
            <span>{dark ? 'Light' : 'Dark'}</span>
          </button>
          <a className="join" href="http://localhost:5174">
            Studio <ArrowUpRight size={16} />
          </a>
        </div>
      </header>

      <section className="ticker">
        <span className="live-dot" /> <b>NOW READING</b>
        <span>Designing a life with more room to breathe</span>
        <ArrowUpRight size={15} />
      </section>

      {articleSlug ? (
        <ApiArticleReader slug={articleSlug} />
      ) : route === '/article' ? (
        <ArticlePage
          story={selectedStory}
          saved={saved.includes((selectedStory ?? news.hero).title)}
          onSave={() => toggleSave((selectedStory ?? news.hero).title)}
        />
      ) : route === '/weather' ? (
        <WeatherPage />
      ) : route === '/' ? (
        <section className="news-layout">
          <NewsDashboard />
          <TrendingRail />
        </section>
      ) : (
        <section className="page-state">
          <p className="eyebrow">
            <span /> 404
          </p>
          <h1>This page isn’t forged yet.</h1>
          <Link className="read-button" to="/">
            Return home <ArrowUpRight size={18} />
          </Link>
        </section>
      )}
      <footer>
        <Link className="brand" to="/">
          news<span>forge</span>
          <i>.</i>
        </Link>
        <span>© 2026 NewsForge. Made for the curious.</span>
        <div>
          <a href="#about">About</a>
          <a href="#contact">Contact</a>
          <a href="#privacy">Privacy</a>
        </div>
      </footer>
      {searchOpen && <SearchPanel close={() => setSearchOpen(false)} />}
    </main>
  )
}
export default App

createRoot(document.getElementById('root')!).render(
  <BrowserRouter>
    <App />
  </BrowserRouter>
)
