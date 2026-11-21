import { useState } from 'react'
import type { FormEvent } from 'react'
import { streamDraft } from '../api/draft'
import { useStreamTask } from '../hooks/useStreamTask'
import type { Company, DraftRequestBody, DraftResult, Person, Tone } from '../types'
import { ErrorBanner } from './ErrorBanner'
import { EvidenceQuote } from './EvidenceQuote'
import { Alert, ArrowRight, Refresh } from './icons'
import { FactMeta } from './FactMeta'
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

const PITCH_MIN = 10
const PITCH_MAX = 600
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
  const result = task.result
  const pitchOk = pitch.trim().length >= PITCH_MIN

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

  return (
    <div className="workspace">
      <aside className="brief">
        <form className="card pad stack" onSubmit={handleSubmit}>
          <div>
            <p className="eyebrow">Step 3 · Your brief</p>
            <h1 className="brief-title">Writing to</h1>
          </div>

          <ul className="recipients">
            {founders.map((f) => (
              <li key={f.name}>
                <span className="avatar">{f.name.trim().charAt(0).toUpperCase()}</span>
                <span>
                  <strong>{f.name}</strong>
                  <span className="muted small">{f.role ? `${f.role} · ${company.name}` : company.name}</span>
                </span>
              </li>
            ))}
          </ul>
          <button type="button" className="link-btn align-start" onClick={onChangeFounders} disabled={running}>
            Change recipients
          </button>

          <label className="field">
            <span className="field-label">
              What are you selling or asking for?
              <span className="field-hint">
                {pitch.trim().length}/{PITCH_MAX}
              </span>
            </span>
            <textarea
              className="textarea"
              value={pitch}
              onChange={(e) => setPitch(e.target.value)}
              rows={4}
              minLength={PITCH_MIN}
              maxLength={PITCH_MAX}
              required
              placeholder="e.g. I run a small studio that builds internal tools for remote teams."
            />
          </label>

          <fieldset className="field fieldset-reset">
            <legend className="field-label">Tone</legend>
            <div className="segmented" role="radiogroup" aria-label="Tone">
              {TONES.map((t) => (
                <label key={t.value}>
                  <input type="radio" name="tone" checked={tone === t.value} onChange={() => setTone(t.value)} />
                  {t.label}
                </label>
              ))}
            </div>
          </fieldset>

          {result ? (
            <div className="stack-sm">
              <button type="button" className="btn btn-primary" onClick={() => start(true)} disabled={running || !pitchOk}>
                <Refresh /> Regenerate
              </button>
              <button type="submit" className="btn btn-secondary" disabled={running || !pitchOk}>
                Research again
              </button>
              <p className="small muted">
                Regenerate rewrites using the facts already found. Research again looks for new ones.
              </p>
            </div>
          ) : (
            <button type="submit" className="btn btn-primary btn-lg" disabled={running || !pitchOk}>
              {running ? 'Working…' : 'Write openers'} {!running && <ArrowRight />}
            </button>
          )}
        </form>
      </aside>

      <section className="results" aria-live="polite">
        {task.phase === 'idle' && (
          <div className="empty card">
            <svg viewBox="0 0 120 64" aria-hidden>
              <path d="M4 32 Q60 8 116 32" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              <circle cx="4" cy="32" r="4" fill="currentColor" />
              <circle cx="116" cy="32" r="4" fill="currentColor" />
            </svg>
            <h2>Your openers will appear here</h2>
            <p className="muted">
              Describe what you offer, choose a tone, and we’ll research {founders.map((f) => f.name.split(' ')[0]).join(' and ')} first.
            </p>
          </div>
        )}

        {running && (
          <div className="card pad">
            <p className="eyebrow work-label">Researching and writing</p>
            <ProgressLog messages={task.progress} running={running} />
          </div>
        )}

        {task.phase === 'error' && task.error && (
          <ErrorBanner code={task.error.code} message={task.error.message} onRetry={() => start(false)} />
        )}

        {result && !running && (
          <>
            <div className="section-head">
              <h2>{result.openers.length === 1 ? 'Your opener' : `${result.openers.length} openers`}</h2>
              <span className="muted small">Copy one into your own email. Nothing is sent from here.</span>
            </div>

            {result.used_fallback && (
              <div className="banner banner-warn" role="status">
                <Alert />
                <div className="banner-body">
                  <strong className="banner-title">Based on the company description only</strong>
                  <span className="banner-detail">
                    No personal facts were found about {founders.length > 1 ? 'these founders' : 'this founder'}, so
                    these openers are less specific than usual.
                  </span>
                </div>
              </div>
            )}

            {result.openers.map((opener, i) => (
              <OpenerCard key={`${i}-${opener.text}`} opener={opener} facts={result.facts} />
            ))}

            {result.facts.length > 0 && (
              <details className="disclosure all-facts card pad">
                <summary>Everything we found ({result.facts.length})</summary>
                <ul className="fact-list">
                  {result.facts.map((fact) => (
                    <li key={fact.id}>
                      <FactMeta fact={fact} showPerson />
                      <p className="fact-text">{fact.text}</p>
                      <EvidenceQuote quote={fact.quote} sourceUrl={fact.source_url} sourceLabel={fact.source_title} />
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </>
        )}
      </section>
    </div>
  )
}
