import { useState } from 'react'
import type { Fact, Opener } from '../types'

type Props = {
  opener: Opener
  facts: Fact[]
}

export function OpenerCard({ opener, facts }: Props) {
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'failed'>('idle')
  const used = opener.fact_ids.map((id) => facts.find((f) => f.id === id)).filter((f): f is Fact => !!f)

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
    <article className="card opener">
      <p className="opener-meta">
        To {opener.to} · {opener.angle}
      </p>
      <p className="opener-text">{opener.text}</p>
      <button type="button" onClick={copy}>
        {copyState === 'copied' ? 'Copied' : copyState === 'failed' ? "Couldn't copy, select the text" : 'Copy'}
      </button>

      {used.length > 0 && (
        <details>
          <summary>Based on</summary>
          <ul className="facts">
            {used.map((fact) => (
              <li key={fact.id}>
                {fact.text}
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
    </article>
  )
}
