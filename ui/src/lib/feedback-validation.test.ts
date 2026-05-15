import { describe, it, expect } from 'vitest';
import { validateFeedback, isValid, EMAIL_REGEX, MESSAGE_MIN, MESSAGE_MAX } from './feedback-validation';

describe('validateFeedback', () => {
  const base = { name: '', email: '', type: 'bug', message: 'x'.repeat(200) };

  it('passes with valid data', () => {
    expect(isValid(validateFeedback(base))).toBe(true);
  });

  it('requires type', () => {
    const errors = validateFeedback({ ...base, type: '' });
    expect(errors.type).toBeTruthy();
  });

  it('rejects short message', () => {
    const errors = validateFeedback({ ...base, message: 'short' });
    expect(errors.message).toBeTruthy();
  });

  it('rejects too-long message', () => {
    const errors = validateFeedback({ ...base, message: 'x'.repeat(MESSAGE_MAX + 1) });
    expect(errors.message).toBeTruthy();
  });

  it('rejects invalid email when non-empty', () => {
    const errors = validateFeedback({ ...base, email: 'not-an-email' });
    expect(errors.email).toBeTruthy();
  });

  it('allows empty email', () => {
    const errors = validateFeedback({ ...base, email: '' });
    expect(errors.email).toBeUndefined();
  });

  it('validates correct email', () => {
    const errors = validateFeedback({ ...base, email: 'test@example.com' });
    expect(errors.email).toBeUndefined();
  });

  it('EMAIL_REGEX rejects common bad patterns', () => {
    expect(EMAIL_REGEX.test('a@b')).toBe(false);
    expect(EMAIL_REGEX.test('noatsign')).toBe(false);
  });

  it('MESSAGE_MIN is 200', () => {
    expect(MESSAGE_MIN).toBe(200);
  });

  it('MESSAGE_MAX is 4000', () => {
    expect(MESSAGE_MAX).toBe(4000);
  });
});
