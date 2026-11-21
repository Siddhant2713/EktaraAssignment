import { useState } from 'react'
import type { FormEvent } from 'react'
import './App.css'
import { ErrorBanner } from './components/ErrorBanner'
import { FounderConfirm } from './components/FounderConfirm'
import { ProgressLog } from './components/ProgressLog'
import { useAnalyze } from './hooks/useAnalyze'
import type { Person } from './types'

function App() {
  const [url, setUrl] = useState('')
  const [confirmed, setConfirmed] = useState<Person[] | null>(null)
  const { phase, progress, result, error, analyze, reset } = useAnalyze()

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setConfirmed(null)
    analyze(url)
  }

  return (
    <main>
      <h1>Ektara</h1>
      <form onSubmit={handleSubmit} className="url-form">
        <input
          type="url"
          placeholder="https://example.com"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          required
        />
        <button type="submit" disabled={phase === 'analyzing'}>
          {phase === 'analyzing' ? 'Working…' : 'Go'}
        </button>
      </form>

      <ProgressLog messages={progress} running={phase === 'analyzing'} />

      {phase === 'error' && error && <ErrorBanner code={error.code} message={error.message} onRetry={reset} />}

      {phase === 'confirm' && result && !confirmed && <FounderConfirm result={result} onConfirm={setConfirmed} />}

      {confirmed && (
        <div className="card">
          <p>Confirmed. Research and drafting come next:</p>
          <ul>
            {confirmed.map((person) => (
              <li key={person.name}>
                <strong>{person.name}</strong>
                {person.role && `, ${person.role}`}
              </li>
            ))}
          </ul>
        </div>
      )}
    </main>
  )
}

export default App
