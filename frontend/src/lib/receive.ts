import type { Stage } from '../api/types';

export interface FailureReason {
  title: string;
  text: string;
}

/**
 * Turn the first failed receiver stage into one plain sentence a non-expert can act on.
 *
 * Wrong-password and no-message look identical in keyed mode on purpose (the receiver cannot even
 * find where the message is), so that case says both.
 */
export function explainFailure(stages: Stage[]): FailureReason | null {
  const failed = stages.find((stage) => stage.status === 'failed');
  if (!failed) return null;
  if (failed.name === 'read_image') {
    return { title: 'This file could not be read', text: 'It does not look like a valid image. Use the PNG you received.' };
  }
  if (failed.name === 'extract_bits' || failed.code === 'NO_HIDDEN_DATA') {
    return {
      title: 'No hidden message found',
      text: 'Either this image holds no message for this password, or the password is wrong. The two look the same on purpose, so nobody can tell whether a message exists without the password.',
    };
  }
  if (failed.name === 'parse_packet') {
    return {
      title: 'A message was found but it is damaged',
      text: 'The image was probably edited, resized or saved as JPEG after the message was hidden.',
    };
  }
  if (failed.name === 'check_sender' || failed.code === 'KEY_MISMATCH') {
    return {
      title: 'Signed by someone else',
      text: 'The message was signed with a different key than the public key you entered. Check that you have the right sender.',
    };
  }
  if (failed.name === 'verify_signature') {
    return {
      title: 'The signature does not match',
      text: 'The image was changed after the sender signed it, or this is not the sender’s key. Nothing was decrypted.',
    };
  }
  if (failed.name === 'derive_key_and_decrypt') {
    return {
      title: 'The message password is wrong',
      text: 'The sender and image are genuine, but this password cannot unlock the message.',
    };
  }
  return { title: 'Verification stopped', text: failed.detail };
}
