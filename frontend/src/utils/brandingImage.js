export const LOGO_CONSTRAINTS = {
  minWidth: 200,
  maxWidth: 2400,
  minHeight: 40,
  maxHeight: 800,
  minRatio: 1.0,
  maxRatio: 6.0,
  maxBytes: 2 * 1024 * 1024,
};

export const FAVICON_CONSTRAINTS = {
  minWidth: 32,
  maxWidth: 512,
  minHeight: 32,
  maxHeight: 512,
  minRatio: 0.9,
  maxRatio: 1.15,
  maxBytes: 2 * 1024 * 1024,
};

export const LOGO_HINT =
  'Landscape PNG, JPEG, or WebP. 200–2400px wide, 40–800px tall, up to 6:1. Max 2MB.';

export const FAVICON_HINT =
  'Nearly square PNG, JPEG, WebP, or ICO. 32–512px. Max 2MB.';

function readImageSize(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      const width = img.naturalWidth;
      const height = img.naturalHeight;
      URL.revokeObjectURL(url);
      resolve({ width, height });
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error('Could not read image. Use PNG, JPEG, WebP, or ICO.'));
    };
    img.src = url;
  });
}

function describe(kind) {
  return kind === 'favicon' ? FAVICON_HINT : LOGO_HINT;
}

export async function validateBrandingImageFile(file, kind) {
  const constraints = kind === 'favicon' ? FAVICON_CONSTRAINTS : LOGO_CONSTRAINTS;
  if (file.size > constraints.maxBytes) {
    throw new Error('File size must be under 2MB');
  }
  const { width, height } = await readImageSize(file);
  const ratio = width / height;
  if (
    width < constraints.minWidth
    || width > constraints.maxWidth
    || height < constraints.minHeight
    || height > constraints.maxHeight
    || ratio < constraints.minRatio
    || ratio > constraints.maxRatio
  ) {
    throw new Error(`This image is ${width}×${height}px. ${describe(kind)}`);
  }
  return { width, height };
}
