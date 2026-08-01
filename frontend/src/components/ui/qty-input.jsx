import * as React from 'react'
import { Input } from './input'
import { cn } from '../../lib/utils'
import { noSpinInputClass } from '../../utils/inputStyles'

/**
 * Compact quantity field for billing / booking line editors.
 * Hides native spin buttons, centers digits, selects on focus.
 */
const QtyInput = React.forwardRef(
  (
    {
      className,
      onFocus,
      size = 'md',
      ...props
    },
    ref
  ) => {
    const handleFocus = (e) => {
      e.target.select()
      onFocus?.(e)
    }

    return (
      <Input
        ref={ref}
        type="number"
        inputMode="decimal"
        onFocus={handleFocus}
        className={cn(
          noSpinInputClass,
          'text-center px-1.5 min-w-0',
          size === 'sm' && 'h-7 text-xs',
          size === 'md' && 'h-9 text-sm',
          className
        )}
        {...props}
      />
    )
  }
)
QtyInput.displayName = 'QtyInput'

export { QtyInput }
