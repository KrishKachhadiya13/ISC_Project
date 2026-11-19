import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { Stage } from '../api/types';
import { ConfidenceGauge } from './ConfidenceGauge';
import { ImageDropzone, validateImageFile } from './ImageDropzone';
import { SecretInput } from './SecretInput';
import { VerificationTimeline } from './VerificationTimeline';

function file(name: string, type: string, size = 100): File {
  return new File([new Uint8Array(size)], name, { type });
}

describe('validateImageFile', () => {
  it('rejects JPEG for embedding with an explanation', () => {
    expect(validateImageFile(file('a.jpg', 'image/jpeg'), true)).toMatch(/lossy/i);
  });
  it('accepts PNG for embedding and JPEG for detection', () => {
    expect(validateImageFile(file('a.png', 'image/png'), true)).toBeNull();
    expect(validateImageFile(file('a.jpg', 'image/jpeg'), false)).toBeNull();
  });
  it('rejects files over 10 MB and non-images', () => {
    expect(validateImageFile(file('big.png', 'image/png', 11 * 1024 * 1024), true)).toMatch(/limit/i);
    expect(validateImageFile(file('notes.txt', 'text/plain'), false)).toMatch(/image/i);
  });
});

describe('ImageDropzone', () => {
  it('shows an alert and does not accept a JPEG in lossless mode', () => {
    const onChange = vi.fn();
    const { container } = render(<ImageDropzone label="Cover" file={null} onChange={onChange} losslessOnly />);
    const input = container.querySelector('input[type=file]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file('photo.jpg', 'image/jpeg')] } });
    expect(screen.getByRole('alert')).toHaveTextContent(/lossy/i);
    expect(onChange).toHaveBeenCalledWith(null);
  });
  it('passes a valid PNG to the parent', () => {
    const onChange = vi.fn();
    const { container } = render(<ImageDropzone label="Cover" file={null} onChange={onChange} losslessOnly />);
    const input = container.querySelector('input[type=file]') as HTMLInputElement;
    const png = file('ok.png', 'image/png');
    fireEvent.change(input, { target: { files: [png] } });
    expect(onChange).toHaveBeenCalledWith(png);
  });
});

describe('VerificationTimeline', () => {
  const stages: Stage[] = [
    { name: 'read_image', status: 'passed', detail: 'Image decoded successfully.', code: null },
    { name: 'verify_signature', status: 'failed', detail: 'Signature invalid.', code: 'VERIFICATION_FAILED' },
    { name: 'derive_key_and_decrypt', status: 'skipped', detail: 'Skipped after an earlier stage failed.', code: null },
  ];
  it('labels every status with words, not only colour', () => {
    render(<VerificationTimeline stages={stages} />);
    expect(screen.getByText(/Passed/)).toBeInTheDocument();
    expect(screen.getByText(/Failed/)).toBeInTheDocument();
    expect(screen.getByText(/Skipped$/)).toBeInTheDocument();
    expect(screen.getByText('[VERIFICATION_FAILED]')).toBeInTheDocument();
  });
  it('renders stages in order', () => {
    render(<VerificationTimeline stages={stages} />);
    const items = screen.getAllByRole('listitem');
    expect(items).toHaveLength(3);
    expect(items[1]).toHaveTextContent('Verify Ed25519 signature');
  });
});

describe('ConfidenceGauge', () => {
  it('exposes the value as text and clamps out-of-range input', () => {
    render(<ConfidenceGauge value={1.7} threshold={0.5} label="Probability" />);
    expect(screen.getByText('100.0%')).toBeInTheDocument();
    expect(screen.getByLabelText(/Probability: 100.0 percent/)).toBeInTheDocument();
  });
});

describe('SecretInput', () => {
  it('toggles visibility with an accessible button', () => {
    render(<SecretInput label="Password" value="abc" onChange={() => undefined} />);
    const input = screen.getByLabelText('Password') as HTMLInputElement;
    expect(input.type).toBe('password');
    fireEvent.click(screen.getByRole('button', { name: /show password/i }));
    expect(input.type).toBe('text');
  });
  it('rates strength and warns when too short', () => {
    const { rerender } = render(<SecretInput label="Pw" value="abc" onChange={() => undefined} showStrength />);
    expect(screen.getByText('Too short')).toBeInTheDocument();
    rerender(<SecretInput label="Pw" value="Correct-Horse-Battery-9!" onChange={() => undefined} showStrength />);
    expect(screen.getByText('Strong')).toBeInTheDocument();
  });
});
