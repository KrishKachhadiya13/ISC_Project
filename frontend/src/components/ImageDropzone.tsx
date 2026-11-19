import { ImagePlus, X } from 'lucide-react';
import { useEffect, useId, useRef, useState } from 'react';

import { formatBytes } from '../lib/format';

export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
const LOSSLESS_TYPES = ['image/png', 'image/bmp', 'image/x-portable-graymap', 'image/x-ms-bmp'];
const LOSSLESS_EXTENSIONS = /\.(png|bmp|pgm)$/i;

export function isJpeg(file: File): boolean {
  return file.type === 'image/jpeg' || /\.jpe?g$/i.test(file.name);
}

/** Client-side guard; the server still validates by decoding. */
export function validateImageFile(file: File, losslessOnly: boolean): string | null {
  if (file.size > MAX_UPLOAD_BYTES) {
    return `File is ${formatBytes(file.size)}; the limit is ${formatBytes(MAX_UPLOAD_BYTES)}.`;
  }
  if (losslessOnly && isJpeg(file)) {
    return 'JPEG is lossy; hidden bits would be destroyed. Use PNG, BMP or PGM.';
  }
  if (losslessOnly && !LOSSLESS_TYPES.includes(file.type) && !LOSSLESS_EXTENSIONS.test(file.name)) {
    return 'Use a lossless PNG, BMP or PGM image.';
  }
  if (!losslessOnly && !file.type.startsWith('image/') && !LOSSLESS_EXTENSIONS.test(file.name)) {
    return 'That file does not look like an image.';
  }
  return null;
}

interface Props {
  label: string;
  file: File | null;
  onChange: (file: File | null) => void;
  losslessOnly?: boolean;
  description?: string;
}

export function ImageDropzone({ label, file, onChange, losslessOnly = false, description }: Props) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);

  useEffect(() => {
    if (!file) {
      setPreview(null);
      return undefined;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  function accept(candidate: File | undefined) {
    if (!candidate) return;
    const problem = validateImageFile(candidate, losslessOnly);
    setError(problem);
    onChange(problem ? null : candidate);
  }

  return (
    <div>
      <label htmlFor={inputId} className="field-label">
        {label}
      </label>
      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          accept(event.dataTransfer.files[0]);
        }}
        className={`relative flex min-h-40 flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-4 text-center transition-colors ${
          dragging ? 'border-accent bg-accent/5' : 'border-line'
        }`}
      >
        {preview && file ? (
          <div className="flex w-full flex-col items-center gap-3">
            <img
              src={preview}
              alt={`Preview of ${file.name}`}
              className="max-h-48 rounded-lg border border-line object-contain"
            />
            <div className="min-w-0 max-w-full text-center text-sm">
              <p className="truncate font-semibold">{file.name}</p>
              <p className="mono text-muted">{formatBytes(file.size)}</p>
              <button type="button" className="btn-ghost mt-2 px-0" onClick={() => onChange(null)}>
                <X className="h-4 w-4" aria-hidden="true" /> Remove
              </button>
            </div>
          </div>
        ) : (
          <>
            <ImagePlus className="h-8 w-8 text-muted" aria-hidden="true" />
            <p className="text-sm">
              <button type="button" className="font-semibold text-accent underline" onClick={() => inputRef.current?.click()}>
                Choose an image
              </button>{' '}
              or drag it here
            </p>
            <p className="text-xs text-muted">
              {description ?? (losslessOnly ? 'PNG, BMP or PGM · up to 10 MB' : 'Any image · up to 10 MB')}
            </p>
          </>
        )}
        <input
          id={inputId}
          ref={inputRef}
          type="file"
          accept={losslessOnly ? '.png,.bmp,.pgm,image/png,image/bmp' : 'image/*,.pgm'}
          className="sr-only"
          onChange={(event) => {
            accept(event.target.files?.[0]);
            event.target.value = '';
          }}
        />
      </div>
      {error && (
        <p role="alert" className="mt-2 text-sm text-bad">
          {error}
        </p>
      )}
    </div>
  );
}
