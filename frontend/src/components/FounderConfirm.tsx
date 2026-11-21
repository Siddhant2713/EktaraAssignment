import { useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import type { AnalyzeResult, Person } from '../types'
import { EvidenceQuote } from './EvidenceQuote'
import { ArrowRight, Close, Plus } from './icons'

const MAX_PEOPLE = 2 // one email goes to one person; two keeps research time reasonable

type Props = {
  result: AnalyzeResult
  onConfirm: (people: Person[]) => void
}

type Entry = {
  id: number
  name: string
  role: string
  checked: boolean
  confidence?: number // only for people the backend found; hand-added ones have none
  evidence?: string
  sourceUrl?: string
  source?: 'site' | 'web'
}

const initial = (name: string) => name.trim().charAt(0).toUpperCase() || '?'

export function FounderConfirm({ result, onConfirm }: Props) {
  const { company, founders, pages_scraped } = result

  const nextId = useRef(founders.length)
  const [entries, setEntries] = useState<Entry[]>(() =>
    founders.map((f, i) => ({
      id: i,
      name: f.name,
      role: f.role ?? '',
      checked: i < MAX_PEOPLE,
      confidence: f.confidence,
      evidence: f.evidence,
      sourceUrl: f.source_url,
      source: f.source,
    })),
  )
  const [newName, setNewName] = useState('')
  const [newRole, setNewRole] = useState('')

  const selected = entries.filter((e) => e.checked && e.name.trim())
  const atLimit = selected.length >= MAX_PEOPLE

  function update(id: number, patch: Partial<Entry>) {
    setEntries((prev) => prev.map((e) => (e.id === id ? { ...e, ...patch } : e)))
  }

  function addPerson() {
    if (!newName.trim()) return
    const id = nextId.current++
    setEntries((prev) => [...prev, { id, name: newName.trim(), role: newRole.trim(), checked: !atLimit }])
    setNewName('')
    setNewRole('')
  }

  function handleAddKey(e: KeyboardEvent) {
    if (e.key === 'Enter') {
      e.preventDefault() // Enter here adds a person; it must not submit the whole form
      addPerson()
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    onConfirm(selected.map((e) => ({ name: e.name.trim(), role: e.role.trim() })))
  }

  return (
    <form className="confirm" onSubmit={handleSubmit}>
      <header className="company-head card pad">
        <span className="avatar avatar-lg">{initial(company.name)}</span>
        <div>
          <p className="eyebrow">Step 2 · Who should it go to?</p>
          <h1 className="page-title">{company.name}</h1>
          <p className="page-sub">{company.one_liner}</p>
        </div>
      </header>

      <section aria-labelledby="people-title">
        <div className="section-head">
          <h2 id="people-title">{founders.length ? 'Founders we found' : 'Who is the founder?'}</h2>
          <span className="muted small">
            {founders.length
              ? `Pick up to ${MAX_PEOPLE}. Fix any names that look off.`
              : 'We couldn’t find anyone on the site or the web. Add a founder below.'}
          </span>
        </div>

        <ul className="people">
          {entries.map((entry) => (
            <li key={entry.id} className={`person card${entry.checked ? ' is-selected' : ''}`}>
              <div className="person-main">
                <input
                  type="checkbox"
                  className="check"
                  checked={entry.checked}
                  disabled={!entry.checked && atLimit}
                  onChange={(e) => update(entry.id, { checked: e.target.checked })}
                  aria-label={`Include ${entry.name}`}
                />
                <span className="avatar">{initial(entry.name)}</span>
                <div className="person-fields">
                  <input
                    className="input input-quiet person-name"
                    value={entry.name}
                    onChange={(e) => update(entry.id, { name: e.target.value })}
                    aria-label="Name"
                    required
                  />
                  <input
                    className="input input-quiet person-role"
                    value={entry.role}
                    onChange={(e) => update(entry.id, { role: e.target.value })}
                    placeholder="Role"
                    aria-label="Role"
                  />
                </div>
                <div className="person-meta">
                  {entry.source ? (
                    <span className={`chip ${entry.source === 'site' ? 'chip-ok' : 'chip-accent'}`}>
                      {entry.source === 'site' ? 'Company site' : 'Web search'}
                    </span>
                  ) : (
                    <>
                      <span className="chip">Added by you</span>
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm icon-only"
                        onClick={() => setEntries((prev) => prev.filter((e) => e.id !== entry.id))}
                        aria-label={`Remove ${entry.name}`}
                      >
                        <Close />
                      </button>
                    </>
                  )}
                  {entry.confidence !== undefined && (
                    <span className="confidence" title="How sure the model is that this person is a founder">
                      <span className="confidence-bar">
                        <span style={{ width: `${Math.round(entry.confidence * 100)}%` }} />
                      </span>
                      {Math.round(entry.confidence * 100)}%
                    </span>
                  )}
                </div>
              </div>
              {entry.evidence && entry.sourceUrl && (
                <div className="person-evidence">
                  <EvidenceQuote
                    quote={entry.evidence}
                    sourceUrl={entry.sourceUrl}
                    sourceLabel={entry.source === 'web' ? 'Web search result' : 'Company site'}
                  />
                </div>
              )}
            </li>
          ))}

          <li className="person person-add card">
            <Plus className="add-icon" />
            <input
              className="input"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={handleAddKey}
              placeholder="Add someone: name"
              aria-label="New person's name"
            />
            <input
              className="input"
              value={newRole}
              onChange={(e) => setNewRole(e.target.value)}
              onKeyDown={handleAddKey}
              placeholder="Role"
              aria-label="New person's role"
            />
            <button type="button" className="btn btn-secondary" onClick={addPerson} disabled={!newName.trim()}>
              Add
            </button>
          </li>
        </ul>
      </section>

      {pages_scraped.length > 0 && (
        <details className="disclosure">
          <summary>{pages_scraped.length} site page(s) read</summary>
          <ul className="pages">
            {pages_scraped.map((page) => (
              <li key={page}>
                <a href={page} target="_blank" rel="noreferrer">
                  {page}
                </a>
              </li>
            ))}
          </ul>
        </details>
      )}

      <div className="actionbar">
        <span className="small muted">
          {selected.length} of {MAX_PEOPLE} selected
        </span>
        <button type="submit" disabled={selected.length === 0} className="btn btn-primary btn-lg">
          Continue <ArrowRight />
        </button>
      </div>
    </form>
  )
}
