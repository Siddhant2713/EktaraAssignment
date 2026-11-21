type Props = {
  messages: string[]
  running: boolean
}

export function ProgressLog({ messages, running }: Props) {
  if (messages.length === 0) return null
  return (
    <ul className="progress">
      {messages.map((message, i) => {
        const isLast = i === messages.length - 1
        return (
          <li key={i} className={running && isLast ? 'active' : 'done'}>
            <span className="marker">{running && isLast ? '…' : '✓'}</span>
            {message}
          </li>
        )
      })}
    </ul>
  )
}
