import { Check } from './icons'

type Props = {
  messages: string[]
  running: boolean
}

// The backend's progress lines as a "string" with a bead per step; the newest one pulses while work continues.
export function ProgressLog({ messages, running }: Props) {
  if (messages.length === 0) return null
  return (
    <ol className="timeline" aria-live="polite">
      {messages.map((message, i) => {
        const active = running && i === messages.length - 1
        return (
          <li key={i} className={active ? 'active' : 'done'}>
            <span className="bead">{!active && <Check />}</span>
            <span>{message}</span>
          </li>
        )
      })}
    </ol>
  )
}
