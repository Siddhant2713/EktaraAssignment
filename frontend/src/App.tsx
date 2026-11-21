import { useState } from 'react'
import type { FormEvent } from 'react'
import './App.css'
import { streamAnalyze } from './api/analyze'
import { DraftPanel } from './components/DraftPanel'
import { ErrorBanner } from './components/ErrorBanner'
import { FounderConfirm } from './components/FounderConfirm'
import { ProgressLog } from './components/ProgressLog'
import { useStreamTask } from './hooks/useStreamTask'
import type { AnalyzeResult, Person } from './types'

function App() {
  const [url, setUrl] = useState('')
  const [analyzedUrl, setAnalyzedUrl] = useState('') // the URL that was analyzed, even if the input is edited later
  const [confirmed, setConfirmed] = useState<Person[] | null>(null)
  const analysis = useStreamTask<string, AnalyzeResult>(streamAnalyze)
  const running = analysis.phase === 'running'

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setConfirmed(null)
    setAnalyzedUrl(url)
    analysis.run(url)
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
        <button type="submit" disabled={running}>
          {running ? 'Working…' : 'Go'}
        </button>
      </form>

      {!confirmed && <ProgressLog messages={analysis.progress} running={running} />}

      {analysis.phase === 'error' && analysis.error && (
        <ErrorBanner code={analysis.error.code} message={analysis.error.message} onRetry={analysis.reset} />
      )}

      {analysis.phase === 'done' && analysis.result && !confirmed && (
        <FounderConfirm result={analysis.result} onConfirm={setConfirmed} />
      )}

      {analysis.phase === 'done' && analysis.result && confirmed && (
        <DraftPanel
          key={confirmed.map((p) => p.name).join('|')}
          url={analyzedUrl}
          company={analysis.result.company}
          founders={confirmed}
          onChangeFounders={() => setConfirmed(null)}
        />
      )}
    </main>
  )
}

export default App
