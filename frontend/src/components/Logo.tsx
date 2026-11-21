// The ektara is a one-stringed instrument: a round body, a neck, and a single string.
export function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <path d="M16 3v13" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
      <circle cx="16" cy="22.5" r="7.5" fill="currentColor" />
      <circle cx="16" cy="22.5" r="2.4" fill="var(--bg)" />
    </svg>
  )
}
