import { Check } from './icons'

const STEPS = ['Site', 'Founders', 'Openers']

export function Stepper({ current }: { current: number }) {
  return (
    <ol className="stepper" aria-label="Progress">
      {STEPS.map((label, i) => (
        <li
          key={label}
          className={i < current ? 'is-done' : i === current ? 'is-current' : ''}
          aria-current={i === current ? 'step' : undefined}
        >
          <span className="stepper-dot">{i < current ? <Check /> : i + 1}</span>
          <span className="stepper-label">{label}</span>
        </li>
      ))}
    </ol>
  )
}
