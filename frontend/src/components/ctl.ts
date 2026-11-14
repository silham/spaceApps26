/** Figma local components "Control / Outline|Primary|Evidence" and "Badge / Warning|Neutral". */
export type ControlVariant = 'outline' | 'primary' | 'evidence' | 'warning' | 'neutral'

export const ctl = (variant: ControlVariant, extra = '') => `ctl ctl--${variant}${extra ? ` ${extra}` : ''}`
