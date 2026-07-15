export const DEPARTMENTS = ["HR", "IT", "Finance", "Operations", "Sales", "Marketing", "Security"] as const;

export const ADMIN_ROLES = [
  "System Administrator",
  "Security Administrator",
  "HR Administrator",
  "Compliance Administrator",
] as const;

export const EMPLOYEE_ROLES = [
  "HR Officer",
  "Recruitment Coordinator",
  "Payroll Specialist",
  "Finance Assistant",
  "IT Support Analyst",
  "Operations Coordinator",
] as const;

export const PRESENCE_STATUSES = ["online", "away", "home", "offline"] as const;

export const EMAIL_RE = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;

export function validatePassword(pw: string): string | null {
  if (pw.length < 8) return "Password must be at least 8 characters.";
  if (!/[A-Z]/.test(pw)) return "Password must include an uppercase letter.";
  if (!/[a-z]/.test(pw)) return "Password must include a lowercase letter.";
  if (!/[0-9]/.test(pw)) return "Password must include a number.";
  if (!/[^A-Za-z0-9]/.test(pw)) return "Password must include a special character.";
  return null;
}
