export type WeatherSnapshot = {
  location: string
  country: string
  temperature: number
  feelsLike: number
  condition: string
  description: string
  icon: string
  humidity: number
  windSpeed: number
  visibility: number | null
  pressure: number
  clouds: number
  sunrise: number
  sunset: number
  observedAt: number
}
export type ForecastPoint = { timestamp: number; temperature: number; condition: string; icon: string }

type CachedWeather = { cachedAt: number; data: WeatherSnapshot; forecast: ForecastPoint[] }
type Coordinates = { lat: number; lon: number }
export type WeatherLocation = Coordinates & { name?: string; country?: string }

const CACHE_KEY = 'newsforge.weather.current.v1'
export const WEATHER_CACHE_MS = 60 * 60 * 1000
const FALLBACK_COORDINATES: Coordinates = { lat: 28.6139, lon: 77.209 }

function readCache(location: Coordinates): CachedWeather | null {
  try {
    const cacheKey = `${CACHE_KEY}.${location.lat.toFixed(2)}.${location.lon.toFixed(2)}`
    const cached = JSON.parse(localStorage.getItem(cacheKey) ?? 'null') as CachedWeather | null
    return cached?.data && Array.isArray(cached.forecast) && Date.now() - cached.cachedAt < WEATHER_CACHE_MS
      ? cached
      : null
  } catch {
    return null
  }
}

function getCoordinates(): Promise<Coordinates> {
  return new Promise((resolve) => {
    if (!navigator.geolocation) return resolve(FALLBACK_COORDINATES)
    navigator.geolocation.getCurrentPosition(
      (position) => resolve({ lat: position.coords.latitude, lon: position.coords.longitude }),
      () => resolve(FALLBACK_COORDINATES),
      { enableHighAccuracy: false, timeout: 8000, maximumAge: WEATHER_CACHE_MS }
    )
  })
}

function formatWeather(payload: any): WeatherSnapshot {
  return {
    location: payload.name,
    country: payload.sys.country,
    temperature: Math.round(payload.main.temp),
    feelsLike: Math.round(payload.main.feels_like),
    condition: payload.weather[0].main,
    description: payload.weather[0].description,
    icon: payload.weather[0].icon,
    humidity: payload.main.humidity,
    windSpeed: Math.round(payload.wind.speed * 3.6),
    visibility: payload.visibility ? Math.round(payload.visibility / 1000) : null,
    pressure: payload.main.pressure,
    clouds: payload.clouds.all,
    sunrise: payload.sys.sunrise,
    sunset: payload.sys.sunset,
    observedAt: payload.dt,
  }
}

export async function getWeather(
  location?: WeatherLocation,
  force = false
): Promise<{ data: WeatherSnapshot; forecast: ForecastPoint[]; cached: boolean }> {
  const coordinates = location ?? (await getCoordinates())
  if (!force) {
    const cached = readCache(coordinates)
    if (cached) return { data: cached.data, forecast: cached.forecast, cached: true }
  }

  const apiKey = import.meta.env.VITE_OPENWEATHER_API_KEY

  if (!apiKey) throw new Error('Weather is not configured. Add VITE_OPENWEATHER_API_KEY to your .env file.')

  const { lat, lon } = coordinates
  const query = `lat=${lat}&lon=${lon}&units=metric&appid=${encodeURIComponent(apiKey)}`
  const [response, forecastResponse] = await Promise.all([
    fetch(`https://api.openweathermap.org/data/2.5/weather?${query}`),
    fetch(`https://api.openweathermap.org/data/2.5/forecast?${query}`),
  ])
  if (!response.ok)
    throw new Error(
      response.status === 401
        ? 'The weather API key is invalid or not active yet.'
        : 'Weather is temporarily unavailable. Please try again.'
    )

  const data = formatWeather(await response.json())
  const forecastPayload = forecastResponse.ok ? await forecastResponse.json() : { list: [] }
  const forecast = (forecastPayload.list as any[])
    .filter((item, index) => item.dt_txt.includes('12:00:00') || index === 0)
    .slice(0, 5)
    .map((item) => ({
      timestamp: item.dt,
      temperature: Math.round(item.main.temp),
      condition: item.weather[0].main,
      icon: item.weather[0].icon,
    }))
  localStorage.setItem(
    `${CACHE_KEY}.${lat.toFixed(2)}.${lon.toFixed(2)}`,
    JSON.stringify({ cachedAt: Date.now(), data, forecast })
  )
  return { data, forecast, cached: false }
}

export function cacheAge(observedAt: number) {
  return new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' }).format(observedAt * 1000)
}
