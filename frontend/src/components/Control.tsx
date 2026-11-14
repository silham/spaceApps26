import type { ReactNode } from 'react'

import { ctl, type ControlVariant } from './ctl'

/** Dropdown drawn as a Figma control: the native select plus the frame's ⌄ glyph. */
export function SelectControl({
  label,
  value,
  options,
  onChange,
  prefix,
  variant = 'outline',
  disabled,
  title,
  className,
}: {
  label: string
  value: string
  options: { value: string; label: string }[]
  onChange?: (value: string) => void
  prefix?: ReactNode
  variant?: ControlVariant
  disabled?: boolean
  title?: string
  className?: string
}) {
  return (
    <label className={ctl(variant, `select${className ? ` ${className}` : ''}`)} title={title}>
      {prefix}
      <select aria-label={label} value={value} disabled={disabled} onChange={(e) => onChange?.(e.target.value)}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <span aria-hidden="true"> ⌄</span>
    </label>
  )
}
