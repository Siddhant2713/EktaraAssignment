import { useState } from 'react'
import type { FormEvent } from 'react'
import { streamDraft } from '../api/draft'
import { useStreamTask } from '../hooks/useStreamTask'
import type { Company, DraftRequestBody, DraftResult, Person, Tone } from '../types'
import { ErrorBanner } from './ErrorBanner'
import { OpenerCard } from './OpenerCard'
import { ProgressLog } from './ProgressLog'

type Props = {
  url: string
  company: Company
  founders: Person[]
  onChangeFounders: () => void
}

const TONES: { value: Tone; label: string }[] = [
  { value: 'casual', label: 'Casual' },
  { value: 'formal', label: 'Formal' },
  { value: 'short', label: 'Short' },
]

const PITCH_KEY = 'ektara.pitch'

// localStorage can be missing or blocked, so it is only ever a convenience
function loadPitch(): string {
  try {
    return localStorage.getItem(PITCH_KEY) ?? ''
  } catch {
    return ''
  }
}

function savePitch(pitch: string) {
  try {
    localStorage.setItem(PITCH_KEY, pitch)
  } catch {
    /* ignore */
  }
}

export function DraftPanel({ url, company, founders, onChangeFounders }: Props) {
  const [pitch, setPitch] = useState(loadPitch)
  const [tone, setTone] = useState<Tone>('casual')
  const task = useStreamTask<DraftRequestBody, DraftResult>(streamDraft)
  const running = task.phase === 'running'

  function start(reuseFacts: boolean) {
    const trimmed = pitch.trim()
    savePitch(trimmed)
    task.run({
      url,
      company,
      founders,
      pitch: trimmed,
      tone,
      facts: reuseFacts ? task.result?.facts : undefined,
    })
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    start(false)
  }

  const result = task.result

  return (
    <>
      <section className="card">
        <p className="panel-head">
          Writing to <strong>{founders.map((f) => f.name).join(' and ')}</strong> at {company.name}{' '}
          <button type="button" className="link" onClick={onChangeFounders} disabled={running}>
            change
          </button>
        </p>

        <form onSubmit={handleSubmit}>
          <label>
            What are you selling or asking for?
            <textarea
              value={pitch}
              onChange={(e) => setPitch(e.target.value)}
              rows={3}
              minLength={10}
              maxLength={600}
              required
              placeholder="e.g. I run a small studio that builds internal tools for remote teams."
            />
          </label>

          <div className="tones" role="radiogroup" aria-label="Tone">
            {TONES.map((t) => (
              <label key={t.value}>
                <input type="radio" name="tone" checked={tone === t.value} onChange={() => setTone(t.value)} />
                {t.label}
              </label>
            ))}
          </div>

          <div className="actions">
            {result ? (
              <>
                <button type="button" onClick={() => start(true)} disabled={running || pitch.trim().length < 10}>
                  Regenerate
                </button>
                <button type="submit" disabled={running}>
                  Research again
                </button>
              </>
            ) : (
              <button type="submit" disabled={running}>
                {running ? 'Working…' : 'Write openers'}
              </button>
            )}
          </div>
        </form>
      </section>

      <ProgressLog messages={task.progress} running={running} />

      {task.phase === 'error' && task.error && (
        <ErrorBanner code={task.error.code} message={task.error.message} onRetry={() => start(false)} />
      )}

      {result && (
        <>
          {result.used_fallback && (
            <p className="notice">
              No personal facts were found about {founders.length > 1 ? 'these founders' : 'this founder'}, so these
              openers are based on the company description only.
            </p>
          )}
          {result.openers.map((opener, i) => (
            <OpenerCard key={`${i}-${opener.text}`} opener={opener} facts={result.facts} />
          ))}
          {result.facts.length > 0 && (
            <details className="all-facts">
              <summary>Everything we found ({result.facts.length})</summary>
              <ul className="facts">
                {result.facts.map((fact) => (
                  <li key={fact.id}>
                    <strong>{fact.person}:</strong> {fact.text}
                    <p className="evidence">
                      “{fact.quote}”{' '}
                      <a href={fact.source_url} target="_blank" rel="noreferrer">
                        {fact.source_title}
                      </a>
                    </p>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}
    </>
  )
}
