import { ErrorBanner } from '../components/ErrorBanner'
import { ProgressLog } from '../components/ProgressLog'
import type { ErrorInfo, Phase } from '../hooks/useStreamTask'

type Props = {
  url: string
  phase: Phase
  progress: string[]
  error: ErrorInfo | null
  onCancel: () => void // back to the landing page; also used by "try again"
}

export function Analyzing({ url, phase, progress, error, onCancel }: Props) {
  const running = phase === 'running'
  return (
    <div className="narrow">
      <p className="eyebrow">Step 1 · Reading the site</p>
      <h1 className="page-title">{running ? 'Looking into it…' : 'That didn’t work'}</h1>
      <p className="page-sub url-echo">{url}</p>

      <div className="card pad">
        {progress.length === 0 && running && <p className="muted">Starting up…</p>}
        <ProgressLog messages={progress} running={running} />
      </div>

      {phase === 'error' && error && (
        <ErrorBanner code={error.code} message={error.message} onRetry={onCancel} retryLabel="Try another URL" />
      )}

      {running && (
        <button type="button" className="btn btn-ghost" onClick={onCancel}>
          Cancel
        </button>
      )}
    </div>
  )
}
