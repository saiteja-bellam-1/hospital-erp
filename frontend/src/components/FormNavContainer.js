import React, { forwardRef } from 'react';
import { cn } from '../lib/utils';
import { NAV_ROOT_ATTR } from '../utils/formNavigation';

/**
 * Marks a navigation scope (form section, dialog body, page form).
 * Keyboard handling is global via FormNavProvider.
 *
 * @param {'linear' | 'grid' | 'table'} mode
 * @param {string | React.ElementType} [tag='div'] - Root element (e.g. 'form')
 */
const FormNavContainer = forwardRef(function FormNavContainer({
  mode = 'linear',
  className,
  children,
  tag: Tag = 'div',
  ...props
}, ref) {
  const Root = (typeof Tag === 'string' || typeof Tag === 'function') ? Tag : 'div';

  return (
    <Root
      ref={ref}
      {...{ [NAV_ROOT_ATTR]: '' }}
      data-form-nav-mode={mode}
      className={cn(className)}
      {...props}
    >
      {children}
    </Root>
  );
});

FormNavContainer.displayName = 'FormNavContainer';

export default FormNavContainer;
