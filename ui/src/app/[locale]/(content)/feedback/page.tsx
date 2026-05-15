'use client';

import { useState, useEffect } from 'react';
import { usePathname } from '@/i18n/navigation';
import { toDevanagariNumerals } from '@/lib/format/devanagari';
import {
  validateFeedback,
  isValid,
  EMAIL_REGEX,
  MESSAGE_MIN,
  MESSAGE_MAX,
  type FeedbackErrors,
} from '@/lib/feedback-validation';

const FEEDBACK_TYPES = [
  { value: 'bug', labelHi: 'बग रिपोर्ट', labelEn: 'Bug Report' },
  { value: 'suggestion', labelHi: 'सुझाव', labelEn: 'Suggestion' },
  { value: 'content_error', labelHi: 'सामग्री त्रुटि', labelEn: 'Content Error' },
] as const;

const inputClass =
  'border border-border rounded-[var(--radius-md)] px-3 py-2 text-foreground bg-surface w-full focus:outline-none focus:ring-2 focus:ring-ring/50';

export default function FeedbackPage() {
  const pathname = usePathname();

  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [emailError, setEmailError] = useState('');
  const [type, setType] = useState('');
  const [message, setMessage] = useState('');
  const [route, setRoute] = useState('');
  const [errors, setErrors] = useState<FeedbackErrors>({});
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [serverError, setServerError] = useState('');

  useEffect(() => {
    // Prefer referrer, fall back to current pathname
    const referrer = typeof document !== 'undefined' ? document.referrer : '';
    setRoute(referrer || pathname);
  }, [pathname]);

  function handleEmailBlur() {
    if (email && !EMAIL_REGEX.test(email)) {
      setEmailError('कृपया एक वैध ईमेल पता दर्ज करें।');
    } else {
      setEmailError('');
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setServerError('');

    const validationErrors = validateFeedback({ name, email, type, message });
    setErrors(validationErrors);
    if (!isValid(validationErrors)) return;

    setSubmitting(true);
    try {
      const res = await fetch('/api/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email, type, message, route }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setServerError(
          data?.error === 'invalid_input'
            ? 'कृपया सभी आवश्यक फ़ील्ड भरें।'
            : 'कुछ गड़बड़ी हुई। कृपया पुनः प्रयास करें।',
        );
      } else {
        setSuccess(true);
      }
    } catch {
      setServerError('कुछ गड़बड़ी हुई। कृपया पुनः प्रयास करें।');
    } finally {
      setSubmitting(false);
    }
  }

  const msgLen = message.length;

  if (success) {
    return (
      <div className="max-w-[640px] mx-auto">
        <div className="rounded-[var(--radius-md)] border border-success bg-success/10 p-6">
          <p className="font-serif-hindi text-[length:var(--font-size-body)] font-semibold text-success">
            धन्यवाद! आपकी प्रतिक्रिया मिल गई।
          </p>
          <p className="mt-1 text-sm text-foreground-muted">
            Thank you! Your feedback has been received.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-[640px] mx-auto">
      <div className="rounded-[var(--radius-md)] border border-border bg-surface p-8 shadow-node">
        <h1 className="font-serif-hindi text-[length:var(--font-size-h1)] font-semibold text-foreground">
          प्रतिक्रिया
        </h1>
        <p className="mt-1 text-sm text-foreground-muted">Feedback</p>

        <form onSubmit={handleSubmit} noValidate className="mt-6 space-y-5">
          {/* Name */}
          <div className="space-y-1">
            <label
              htmlFor="fb-name"
              className="block text-sm font-medium text-foreground"
            >
              नाम <span className="text-foreground-muted">(Name)</span>
            </label>
            <input
              id="fb-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className={inputClass}
              autoComplete="name"
            />
          </div>

          {/* Email */}
          <div className="space-y-1">
            <label
              htmlFor="fb-email"
              className="block text-sm font-medium text-foreground"
            >
              ईमेल <span className="text-foreground-muted">(Email)</span>
            </label>
            <input
              id="fb-email"
              type="email"
              value={email}
              onChange={(e) => { setEmail(e.target.value); setEmailError(''); }}
              onBlur={handleEmailBlur}
              className={inputClass}
              autoComplete="email"
            />
            {(emailError || errors.email) && (
              <p className="text-sm text-danger">{emailError || errors.email}</p>
            )}
          </div>

          {/* Type */}
          <fieldset className="space-y-2">
            <legend className="block text-sm font-medium text-foreground">
              प्रकार <span className="text-foreground-muted">(Type)</span>
            </legend>
            <div className="space-y-2">
              {FEEDBACK_TYPES.map((ft) => (
                <label
                  key={ft.value}
                  className="flex cursor-pointer items-center gap-2 text-sm text-foreground"
                >
                  <input
                    type="radio"
                    name="fb-type"
                    value={ft.value}
                    checked={type === ft.value}
                    onChange={() => setType(ft.value)}
                    className="accent-accent"
                  />
                  <span className="font-serif-hindi">{ft.labelHi}</span>
                  <span className="text-foreground-muted">({ft.labelEn})</span>
                </label>
              ))}
            </div>
            {errors.type && (
              <p className="text-sm text-danger">{errors.type}</p>
            )}
          </fieldset>

          {/* Message */}
          <div className="space-y-1">
            <label
              htmlFor="fb-message"
              className="block text-sm font-medium text-foreground"
            >
              संदेश <span className="text-foreground-muted">(Message)</span>
            </label>
            <textarea
              id="fb-message"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              rows={6}
              className={inputClass}
              maxLength={MESSAGE_MAX}
            />
            <p className="text-right text-xs text-foreground-muted">
              {toDevanagariNumerals(msgLen)}/{toDevanagariNumerals(MESSAGE_MAX)}
            </p>
            {errors.message && (
              <p className="text-sm text-danger">{errors.message}</p>
            )}
          </div>

          {/* Hidden route field */}
          <input type="hidden" name="route" value={route} readOnly />

          {/* Server error */}
          {serverError && (
            <p className="text-sm text-danger">{serverError}</p>
          )}

          {/* Submit */}
          <button
            type="submit"
            disabled={submitting}
            style={{ minHeight: '44px' }}
            className="w-full rounded-[var(--radius-md)] bg-accent px-4 py-2 text-sm font-semibold text-accent-foreground hover:bg-accent-hover disabled:opacity-60"
          >
            {submitting ? 'भेज रहे हैं…' : 'भेजें (Submit)'}
          </button>
        </form>
      </div>
    </div>
  );
}
