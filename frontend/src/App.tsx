import { useState } from 'react'
import { streamAnalyze } from './api/analyze'
import { AppShell } from './components/AppShell'
import { DraftPanel } from './components/DraftPanel'
import { FounderConfirm } from './components/FounderConfirm'
import { useStreamTask } from './hooks/useStreamTask'
import { Analyzing } from './pages/Analyzing'
import { Landing } from './pages/Landing'
import type { AnalyzeResult, Person } from './types'

function App() {
  const [url, setUrl] = useState('')
  const [analyzedUrl, setAnalyzedUrl] = useState('') // the URL that was analyzed, even if the input is edited later
  const [confirmed, setConfirmed] = useState<Person[] | null>(null)
  const analysis = useStreamTask<string, AnalyzeResult>(streamAnalyze)

  function startAnalysis() {
    setConfirmed(null)
    setAnalyzedUrl(url)
    analysis.run(url)
  }

  function startOver() {
    setConfirmed(null)
    analysis.reset()
  }

  const result = analysis.phase === 'done' ? analysis.result : null

  return (
    <AppShell step={result ? (confirmed ? 2 : 1) : analysis.phase === 'idle' ? null : 0} onHome={startOver}>
      {analysis.phase === 'idle' && <Landing url={url} onUrlChange={setUrl} onSubmit={startAnalysis} />}

      {(analysis.phase === 'running' || analysis.phase === 'error') && (
        <Analyzing
          url={analyzedUrl}
          phase={analysis.phase}
          progress={analysis.progress}
          error={analysis.error}
          onCancel={startOver}
        />
      )}

      {result && !confirmed && <FounderConfirm result={result} onConfirm={setConfirmed} />}

      {result && confirmed && (
        <DraftPanel
          key={confirmed.map((p) => p.name).join('|')}
          url={analyzedUrl}
          company={result.company}
          founders={confirmed}
          onChangeFounders={() => setConfirmed(null)}
        />
      )}
    </AppShell>
  )
}

export default App
