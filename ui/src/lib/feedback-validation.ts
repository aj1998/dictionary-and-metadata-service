export interface FeedbackData {
  name: string;
  email: string;
  type: string;
  message: string;
}

export interface FeedbackErrors {
  email?: string;
  type?: string;
  message?: string;
}

export const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
export const MESSAGE_MIN = 200;
export const MESSAGE_MAX = 4000;

export function validateFeedback(data: FeedbackData): FeedbackErrors {
  const errors: FeedbackErrors = {};
  if (data.email && !EMAIL_REGEX.test(data.email)) {
    errors.email = 'कृपया एक वैध ईमेल पता दर्ज करें।';
  }
  if (!data.type) {
    errors.type = 'कृपया प्रकार चुनें।';
  }
  if (data.message.length < MESSAGE_MIN) {
    errors.message = `संदेश कम से कम ${MESSAGE_MIN} अक्षर का होना चाहिए।`;
  }
  if (data.message.length > MESSAGE_MAX) {
    errors.message = `संदेश ${MESSAGE_MAX} अक्षर से अधिक नहीं हो सकता।`;
  }
  return errors;
}

export function isValid(errors: FeedbackErrors): boolean {
  return Object.keys(errors).length === 0;
}
