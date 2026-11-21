import { useState } from 'react'
import type { Fact, Opener } from '../types'
import { EvidenceQuote } from './EvidenceQuote'
import { FactMeta } from './FactMeta'
import { Check, Copy } from './icons'

type Props = {
  opener: Opener
  facts: Fact[]
}

export function OpenerCard({ opener, facts }: Props) {
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'failed'>('idle')
  const used = opener.fact_ids.map((id) => facts.find((f) => f.id === id)).filter((f): f is Fact => !!f)
  const words = opener.text.trim().split(/\s+/).length

  async function copy() {
    try {
      await navigator.clipboard.writeText(opener.text)
      setCopyState('copied')
    } catch {
      setCopyState('failed') // clipboard can be blocked; the text stays selectable
    }
    setTimeout(() => setCopyState('idle'), 2000)
  }

  return (
    <article className="opener card">
      <header className="opener-head">
        <span className="avatar">{opener.to.trim().charAt(0).toUpperCase()}</span>
        <div className="opener-to">
          <span className="eyebrow">To</span>
          <strong>{opener.to}</strong>
        </div>
        <span className="chip chip-accent">{opener.angle}</span>
      </header>

      <p className="opener-text">{opener.text}</p>

      <footer className="opener-foot">
        <button type="button" className="btn btn-secondary btn-sm" onClick={copy}>
          {copyState === 'copied' ? <Check /> : <Copy />}
          {copyState === 'copied' ? 'Copied' : copyState === 'failed' ? 'Couldn’t copy, select the text' : 'Copy'}
        </button>
        <span className="small muted">{words} words</span>
      </footer>

      {used.length > 0 && (
        <details className="disclosure opener-based">
          <summary>Based on {used.length === 1 ? '1 fact' : `${used.length} facts`}</summary>
          <ul className="fact-list">
            {used.map((fact) => (
              <li key={fact.id}>
                <FactMeta fact={fact} />
                <p className="fact-text">{fact.text}</p>
                <EvidenceQuote quote={fact.quote} sourceUrl={fact.source_url} sourceLabel={fact.source_title} />
              </li>
            ))}
          </ul>
        </details>
      )}
    </article>
  )
}
