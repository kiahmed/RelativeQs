/** RelativeQs brand mark: a faceted diamond cupped in an open hand
 * ("diamond hands"). Inherits color via currentColor; size via props. */
export default function Logo({ className = '', title = 'RelativeQs' }: { className?: string; title?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      role="img"
      aria-label={title}
      className={className}
    >
      {/* faceted diamond (gem) */}
      <path d="M8 3.2h8l2.4 3.6L12 13 5.6 6.8 8 3.2Z" />
      <path d="M5.6 6.8h12.8M8 3.2 12 13M16 3.2 12 13" />
      {/* open hand cupping the gem */}
      <path d="M4.6 15.2c0 3.6 3.3 5.6 7.4 5.6s7.4-2 7.4-5.6" />
      <path d="M4.6 15.2c-.9-.5-1.7.2-1.4 1.2M19.4 15.2c.9-.5 1.7.2 1.4 1.2" />
      <path d="M8.4 16.4v1.2M12 16.8v1.4M15.6 16.4v1.2" />
    </svg>
  )
}
