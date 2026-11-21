import type { ErrorCode } from '../types'
import { Alert } from './icons'

const HINTS: Record<ErrorCode, string> = {
  CONFIG_MISSING: 'The backend has no Gemini API key. Add it to backend/.env and restart the server.',
  INVALID_URL: 'Check the URL and try again.',
  SITE_UNREACHABLE: 'The site could not be reached. Check the address, or try again in a moment.',
  SITE_BLOCKED: 'The site refuses automated visits, so it cannot be read.',
  NO_CONTENT: 'The page has no readable text. It may build its content with JavaScript.',
  LLM_FAILED: 'The AI step failed. Trying again often works.',
  SEARCH_FAILED: 'The web search returned nothing. Trying again often works.',
  TIMEOUT: 'This took too long and was stopped. Trying again often works.',
  INTERNAL_ERROR: 'Something went wrong.',
}

type Props = {
  code: ErrorCode
  message: string
  onRetry: () => void
  retryLabel?: string
}

export function ErrorBanner({ code, message, onRetry, retryLabel = 'Try again' }: Props) {
  return (
    <div className="banner banner-error" role="alert">
      <Alert />
      <div className="banner-body">
        <strong className="banner-title">{HINTS[code]}</strong>
        <span className="banner-detail">{message}</span>
        <button type="button" className="btn btn-sm" onClick={onRetry}>
          {retryLabel}
        </button>
      </div>
    </div>
  )
}
