import axios from 'axios'
import {
  solarWindData,
  visibilityScore,
  nearbyViewpoints,
  alerts,
} from '../data/mockData'

// ── Axios instance ────────────────────────────────────────────────────────────
// Replace VITE_API_BASE_URL in .env when a real backend is available
const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '',
  timeout: 8000,
  headers: { 'Content-Type': 'application/json' },
})

// ── Feature flag ──────────────────────────────────────────────────────────────
// Set VITE_USE_MOCK_DATA=false in .env to switch to live endpoints
const USE_MOCK = import.meta.env.VITE_USE_MOCK_DATA !== 'false'

// ── Helpers ───────────────────────────────────────────────────────────────────
function handleError(fn, fallback) {
  return async (...args) => {
    try {
      return await fn(...args)
    } catch (err) {
      const status  = err.response?.status
      const message = err.response?.data?.message ?? err.message
      console.warn(`[Aurora API] ${fn.name} failed (${status ?? 'network'}): ${message}`)
      console.info(`[Aurora API] Falling back to mock data for ${fn.name}`)
      return typeof fallback === 'function' ? fallback(...args) : fallback
    }
  }
}

// ── Live fetch functions ──────────────────────────────────────────────────────

async function _fetchSpaceWeather() {
  const { data } = await api.get('/api/space-weather')
  return data
}

async function _fetchVisibility(lat, lon) {
  const { data } = await api.get('/api/visibility', { params: { lat, lon } })
  return data
}

async function _fetchRoute(lat, lon) {
  const { data } = await api.get('/api/route', { params: { lat, lon } })
  return data
}

async function _fetchAlerts() {
  const { data } = await api.get('/api/alerts')
  return data
}

// ── Mock fallback functions ───────────────────────────────────────────────────

function _mockSpaceWeather() {
  return Promise.resolve({
    ...solarWindData,
    source:    'mock',
    fetchedAt: new Date().toISOString(),
  })
}

function _mockVisibility(lat, lon) {
  return Promise.resolve({
    ...visibilityScore,
    lat,
    lon,
    source:    'mock',
    fetchedAt: new Date().toISOString(),
  })
}

function _mockRoute(lat, lon) {
  return Promise.resolve({
    origin:     { lat, lon },
    viewpoints: nearbyViewpoints,
    source:     'mock',
    fetchedAt:  new Date().toISOString(),
  })
}

function _mockAlerts() {
  return Promise.resolve({
    alerts,
    source:    'mock',
    fetchedAt: new Date().toISOString(),
  })
}

// ── Public API ────────────────────────────────────────────────────────────────
// In mock mode, skip network calls entirely.
// In live mode, attempt the real endpoint and fall back to mock on failure.

export const fetchSpaceWeather = USE_MOCK
  ? _mockSpaceWeather
  : handleError(_fetchSpaceWeather, _mockSpaceWeather)

export const fetchVisibility = USE_MOCK
  ? _mockVisibility
  : handleError(_fetchVisibility, _mockVisibility)

export const fetchRoute = USE_MOCK
  ? _mockRoute
  : handleError(_fetchRoute, _mockRoute)

export const fetchAlerts = USE_MOCK
  ? _mockAlerts
  : handleError(_fetchAlerts, _mockAlerts)

export default api