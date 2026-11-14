import type { ReactNode } from 'react'
import chevronDown from '../assets/v2/chevron-down.svg'
import dotInfo from '../assets/v2/dot-info.svg'
import dotNeutral from '../assets/v2/dot-neutral.svg'
import dotSuccess from '../assets/v2/dot-success.svg'
import dotWarning from '../assets/v2/dot-warning.svg'

/** Shared controls from the Figma component set 24:49 ("Components v2"). */

/** A Figma icon in its square slot. The SVG keeps its own exported size and is centred in the slot. */
export function Icon({ src, size }: { src: string; size: number }) {
  return (
    <span className="icon" style={{ width: size, height: size }} aria-hidden="true">
      <img src={src} alt="" />
    </span>
  )
}

export type Tone = 'success' | 'warning' | 'neutral' | 'info'
const DOTS: Record<Tone, string> = { success: dotSuccess, warning: dotWarning, neutral: dotNeutral, info: dotInfo }

/** Pill badge. Renders a button when `onClick` is given. */
export function Badge({
  tone,
  dot = true,
  className = '',
  onClick,
  children,
}: {
  tone: Tone
  dot?: boolean
  className?: string
  onClick?: () => void
  children: ReactNode
}) {
  const classes = `badge badge--${tone} ${className}`.trim()
  const content = (
    <>
      {dot && <img src={DOTS[tone]} alt="" />}
      {children}
    </>
  )
  return onClick ? (
    <button type="button" className={classes} onClick={onClick}>
      {content}
    </button>
  ) : (
    <span className={classes}>{content}</span>
  )
}

/** Dropdown drawn as the Figma "Select": a native select plus the frame's chevron. */
export function SelectControl({
  label,
  value,
  options,
  onChange,
  prefix,
  disabled,
  title,
  className = '',
}: {
  label: string
  value: string
  options: { value: string; label: string }[]
  onChange?: (value: string) => void
  prefix?: ReactNode
  disabled?: boolean
  title?: string
  className?: string
}) {
  return (
    <label className={`select ${className}`.trim()} title={title}>
      {prefix}
      <select aria-label={label} value={value} disabled={disabled} onChange={(e) => onChange?.(e.target.value)}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <Icon src={chevronDown} size={16} />
    </label>
  )
}
