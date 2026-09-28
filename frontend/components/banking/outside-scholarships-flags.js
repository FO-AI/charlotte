/**
 * Flag rules for the outside-scholarships review UI.
 * Single source of truth — the backend does not compute flags.
 */

export const PID_DIGIT_COUNT = 9;

export function isWellFormedPid(pid) {
  const digits = String(pid ?? '').replace(/\D/g, '');
  return digits.length === PID_DIGIT_COUNT;
}

export function normalizePidDigits(pid) {
  return String(pid ?? '').replace(/\D/g, '');
}

/**
 * Highest-priority PID flag for one entry, or null.
 * Order: missing > malformed > lookup_failed > no_ad_match
 */
export function pidEntryFlag(entry) {
  const pid = String(entry?.pid ?? '').trim();
  if (!pid) {
    return {
      type: 'pid_missing',
      message: 'No PID on this check. Enter it from the check image, or mark the check verified.',
    };
  }
  if (!isWellFormedPid(pid)) {
    return {
      type: 'pid_malformed',
      message: 'PIDs are 9 digits. Check the image for a cut-off or misread digit.',
    };
  }
  const status = entry?.active_directory?.status;
  if (status === 'lookup_failed') {
    return {
      type: 'ad_lookup_failed',
      message: "Couldn't reach Active Directory.",
    };
  }
  if (status === 'not_found') {
    return {
      type: 'no_ad_match',
      message: 'No Active Directory account has this PID.',
    };
  }
  return null;
}

function isValidAmount(value) {
  if (value === null || value === undefined) return false;
  const text = String(value).trim();
  if (!text) return false;
  const cleaned = text.replace(/\$/g, '').replace(/,/g, '').replace(/\s/g, '');
  return /^\d+(\.\d{1,2})?$/.test(cleaned);
}

/**
 * Check-level missing required fields flag, or null.
 */
export function checkFieldFlag(check) {
  const missing = [];
  if (!isValidAmount(check?.amount)) missing.push('amount');
  if (!String(check?.check_number ?? '').trim()) missing.push('check number');
  if (!String(check?.provider ?? '').trim()) missing.push('provider');
  if (!missing.length) return null;
  return {
    type: 'missing_required',
    message: `Missing: ${missing.join(', ')}.`,
  };
}

export function checkNeedsReview(check) {
  if (check?.verified) return false;
  if (checkFieldFlag(check)) return true;
  const pids = Array.isArray(check?.pids) && check.pids.length ? check.pids : [{ pid: '' }];
  return pids.some((entry) => Boolean(pidEntryFlag(entry)));
}

export function checkStatus(check) {
  if (check?.verified) return { key: 'verified', label: 'Verified' };
  if (checkNeedsReview(check)) return { key: 'needs_review', label: 'Needs review' };
  return { key: 'ok', label: 'OK' };
}

export function summarizeReview(checks) {
  const list = Array.isArray(checks) ? checks : [];
  let totalAmount = 0;
  let needsReview = 0;
  let pidCount = 0;
  for (const check of list) {
    const pids = Array.isArray(check?.pids) ? check.pids : [];
    pidCount += pids.filter((entry) => String(entry?.pid ?? '').trim()).length;
    const amountText = String(check?.amount ?? '').replace(/\$/g, '').replace(/,/g, '');
    const amount = Number.parseFloat(amountText);
    if (!Number.isNaN(amount)) totalAmount += amount;
    if (checkNeedsReview(check)) needsReview += 1;
  }
  return {
    checkCount: list.length,
    pidCount,
    totalAmount,
    needsReview,
  };
}
