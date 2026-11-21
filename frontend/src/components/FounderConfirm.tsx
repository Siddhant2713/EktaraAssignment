import { useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import type { AnalyzeResult, Person } from '../types'

type Props = {
  result: AnalyzeResult
  onConfirm: (people: Person[]) => void
}

type Entry = {
  id: number
  name: string
  role: string
  checked: boolean
  evidence?: string // only for people the backend found; hand-added ones have none
  sourceUrl?: string
}

export function FounderConfirm({ result, onConfirm }: Props) {
  const { company, founders, pages_scraped } = result

  const nextId = useRef(founders.length)
  const [entries, setEntries] = useState<Entry[]>(() =>
    founders.map((f, i) => ({
      id: i,
      name: f.name,
      role: f.role ?? '',
      checked: true,
      evidence: f.evidence,
      sourceUrl: f.source_url,
    })),
  )
  const [newName, setNewName] = useState('')
  const [newRole, setNewRole] = useState('')

  const selected = entries.filter((e) => e.checked && e.name.trim())

  function update(id: number, patch: Partial<Entry>) {
    setEntries((prev) => prev.map((e) => (e.id === id ? { ...e, ...patch } : e)))
  }

  function addPerson() {
    if (!newName.trim()) return
    const id = nextId.current++
    setEntries((prev) => [...prev, { id, name: newName.trim(), role: newRole.trim(), checked: true }])
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
    <section className="card">
      <h2>{company.name}</h2>
      <p className="muted">{company.one_liner}</p>

      <form onSubmit={handleSubmit}>
        <h3>{founders.length ? 'Who should the email go to?' : 'Who is the founder?'}</h3>
        <p className="muted">
          {founders.length
            ? `Found ${founders.length} on the site. Tick who to write to and fix any names.`
            : "The site doesn't name a founder. Add one below."}
        </p>

        <ul className="people">
          {entries.map((entry) => (
            <li key={entry.id}>
              <div className="person-row">
                <input
                  type="checkbox"
                  checked={entry.checked}
                  onChange={(e) => update(entry.id, { checked: e.target.checked })}
                  aria-label={`Include ${entry.name}`}
                />
                <input
                  value={entry.name}
                  onChange={(e) => update(entry.id, { name: e.target.value })}
                  aria-label="Name"
                  required
                />
                <input
                  value={entry.role}
                  onChange={(e) => update(entry.id, { role: e.target.value })}
                  placeholder="Role"
                  aria-label="Role"
                />
              </div>
              {entry.evidence && (
                <p className="evidence">
                  “{entry.evidence}”{' '}
                  <a href={entry.sourceUrl} target="_blank" rel="noreferrer">
                    source
                  </a>
                </p>
              )}
            </li>
          ))}
        </ul>

        <div className="person-row add-row">
          <span aria-hidden>+</span>
          <input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={handleAddKey}
            placeholder="Add someone: name"
            aria-label="New person's name"
          />
          <input
            value={newRole}
            onChange={(e) => setNewRole(e.target.value)}
            onKeyDown={handleAddKey}
            placeholder="Role"
            aria-label="New person's role"
          />
          <button type="button" onClick={addPerson} disabled={!newName.trim()}>
            Add
          </button>
        </div>

        <button type="submit" disabled={selected.length === 0} className="confirm">
          Confirm{selected.length > 0 ? ` (${selected.length})` : ''}
        </button>
      </form>

      <details>
        <summary>{pages_scraped.length} page(s) read</summary>
        <ul>
          {pages_scraped.map((url) => (
            <li key={url}>
              <a href={url} target="_blank" rel="noreferrer">
                {url}
              </a>
            </li>
          ))}
        </ul>
      </details>
    </section>
  )
}
