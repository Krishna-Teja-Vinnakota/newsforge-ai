export type LocationChoice = { name: string; country: string; lat: number; lon: number }

const SAVED_LOCATION_KEY = 'newsforge.weather.location.v1'

export function readSavedLocation(): LocationChoice | undefined {
  try {
    const value = JSON.parse(localStorage.getItem(SAVED_LOCATION_KEY) ?? 'null')
    return value && typeof value.name === 'string' && typeof value.lat === 'number' && typeof value.lon === 'number' ? value : undefined
  } catch {
    return undefined
  }
}

export function saveLocation(location: LocationChoice) {
  localStorage.setItem(SAVED_LOCATION_KEY, JSON.stringify(location))
}

export async function searchLocations(query: string, signal?: AbortSignal): Promise<LocationChoice[]> {
  const apiKey = import.meta.env.VITE_GEOAPIFY_API_KEY
  if (!apiKey || query.trim().length < 3) return []

  const params = new URLSearchParams({ text: query.trim(), format: 'json', limit: '5', apiKey })
  const response = await fetch(`https://api.geoapify.com/v1/geocode/autocomplete?${params}`, { signal })
  if (!response.ok) throw new Error('Location search is unavailable.')
  const payload = await response.json()
  return (payload.results ?? []).map((result: any) => ({
    name: result.city || result.name || result.formatted,
    country: result.country || '',
    lat: result.lat,
    lon: result.lon,
  }))
}
