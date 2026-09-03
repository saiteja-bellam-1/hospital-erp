import React, { useEffect, useState } from 'react';
import defaultLogo from '../assets/Final Logo KT (1).jpg';
import { useBranding } from '../contexts/BrandingContext';

const VARIANT_CLASS = {
  login: 'block max-h-24 w-auto max-w-[300px] object-contain object-center',
  sidebar: 'block max-h-9 w-auto max-w-[188px] object-contain object-center',
  header: 'block max-h-8 w-auto max-w-[160px] object-contain object-center',
  preview: 'block max-h-16 w-auto max-w-[220px] object-contain object-center',
};

/**
 * Hospital logo with fallback to bundled KT default when missing or broken.
 * Variants cap width and height so landscape wordmarks scale without stretching.
 */
export default function HospitalLogo({
  variant = 'preview',
  className = '',
  alt,
  style,
  src: srcOverride,
  ...props
}) {
  const { hospitalName, logoUrl } = useBranding();
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setFailed(false);
  }, [logoUrl, srcOverride]);

  const src = !failed && (srcOverride || logoUrl) ? (srcOverride || logoUrl) : defaultLogo;
  const variantClass = VARIANT_CLASS[variant] || VARIANT_CLASS.preview;

  return (
    <img
      src={src}
      alt={alt || hospitalName}
      className={`${variantClass} ${className}`.trim()}
      style={style}
      onError={() => setFailed(true)}
      {...props}
    />
  );
}
