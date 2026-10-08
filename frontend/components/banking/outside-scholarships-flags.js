/**
 * Flag rules for the outside-scholarships review UI.
 * Single source of truth — the backend does not compute flags.
 */

export const PID_DIGIT_COUNT = 9;
/** Keep in sync with backend PROVIDER_MAX_LENGTH (Excel data validation). */
export const PROVIDER_MAX_LENGTH = 30;
/** Academic year label for Fall 2026 – Summer 2 2027. Keep in sync with backend DEFAULT_AID_YEAR. */
export const DEFAULT_AID_YEAR = '2027';
/** Keep in sync with backend ALLOWED_AID_TERMS. */
export const ALLOWED_AID_TERMS = ['F', 'S', 'F/S', 'SS1', 'SS2'];
export const DEFAULT_AID_TERM = 'F';

export function isAllowedAidTerm(term) {
  return ALLOWED_AID_TERMS.includes(String(term ?? '').trim().toUpperCase());
}

export function isWellFormedPid(pid) {
  const digits = String(pid ?? '').replace(/\D/g, '');
  return digits.length === PID_DIGIT_COUNT;
}

export function normalizePidDigits(pid) {
  return String(pid ?? '').replace(/\D/g, '');
}

function nonBlankPidEntries(check) {
  const pids = Array.isArray(check?.pids) ? check.pids : [];
  return pids.filter((entry) => String(entry?.pid ?? '').trim());
}

export function hasMultipleNonBlankPids(check) {
  return nonBlankPidEntries(check).length > 1;
}

function normalizeNameTokens(value) {
  return String(value ?? '')
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
    .split(/\s+/)
    .filter(Boolean);
}

function namesLikelyMatch(payeeName, activeDirectoryName) {
  const payeeTokens = normalizeNameTokens(payeeName);
  const adTokens = normalizeNameTokens(activeDirectoryName);
  if (!payeeTokens.length || !adTokens.length) return true;

  const payeeText = payeeTokens.join(' ');
  const adText = adTokens.join(' ');
  if (payeeText === adText) return true;

  const payeeSet = new Set(payeeTokens);
  const adSet = new Set(adTokens);
  const sameTokenSet =
    payeeSet.size === adSet.size && [...payeeSet].every((token) => adSet.has(token));
  if (sameTokenSet) return true;

  let overlap = 0;
  for (const token of payeeSet) {
    if (adSet.has(token)) overlap += 1;
  }
  const subsetMatch = overlap >= 2 && (overlap === payeeSet.size || overlap === adSet.size);
  return subsetMatch;
}

export function hasAdPayeeNameMismatch(check) {
  const payeeName = String(check?.name ?? '').trim();
  if (!payeeName) return false;
  const pids = Array.isArray(check?.pids) ? check.pids : [];
  return pids.some((entry) => {
    if (entry?.active_directory?.status !== 'found') return false;
    const adName = String(entry?.active_directory?.name ?? '').trim();
    if (!adName) return false;
    return !namesLikelyMatch(payeeName, adName);
  });
}

export function checkMultiPidFlag(check) {
  if (!hasMultipleNonBlankPids(check)) return null;
  return {
    type: 'multi_pid',
    shortLabel: 'Multiple PIDs',
    message: 'This check has more than one PID and requires review before export.',
  };
}

export function checkNameMismatchFlag(check) {
  if (!hasAdPayeeNameMismatch(check)) return null;
  return {
    type: 'name_mismatch',
    shortLabel: 'Name mismatch',
    message: 'Payee name and Active Directory name do not match for at least one PID.',
  };
}

/** True when a PID field has text that is not exactly nine digits (blank is OK). */
export function isNonBlankBadPid(pid) {
  const text = String(pid ?? '').trim();
  return Boolean(text) && !isWellFormedPid(text);
}

/** True when any PID on the check is non-blank and malformed. */
export function hasNonBlankBadPid(check) {
  const pids = Array.isArray(check?.pids) ? check.pids : [];
  return pids.some((entry) => isNonBlankBadPid(entry?.pid));
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
      shortLabel: 'No PID',
      message: 'No PID on this check. Enter it from the check image, or mark the check verified.',
    };
  }
  if (!isWellFormedPid(pid)) {
    return {
      type: 'pid_malformed',
      shortLabel: 'Bad PID',
      message: 'PIDs are 9 digits. Check the image for a cut-off or misread digit.',
    };
  }
  // Keep the check in Needs review while AD is in flight so export cannot race ahead,
  // and avoid flashing "No AD match" from a stale status during lookup.
  if (entry?.lookingUp) {
    return {
      type: 'ad_looking_up',
      shortLabel: 'Looking up…',
      message: 'Looking up this PID in Active Directory.',
    };
  }
  const status = entry?.active_directory?.status;
  if (status === 'lookup_failed') {
    return {
      type: 'ad_lookup_failed',
      shortLabel: 'AD unreachable',
      message: "Couldn't reach Active Directory.",
    };
  }
  if (status === 'not_found') {
    return {
      type: 'no_ad_match',
      shortLabel: 'No AD match',
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
 * Which required scalar fields are missing/invalid on a check.
 */
export function missingRequiredFields(check) {
  const missing = [];
  if (!isValidAmount(check?.amount)) missing.push('amount');
  if (!String(check?.check_number ?? '').trim()) missing.push('check number');
  const provider = String(check?.provider ?? '').trim();
  if (!provider) missing.push('provider');
  else if (provider.length > PROVIDER_MAX_LENGTH) missing.push('provider length');
  return missing;
}

/**
 * Check-level missing required fields flag, or null.
 */
export function checkFieldFlag(check) {
  const missing = missingRequiredFields(check);
  if (!missing.length) return null;
  return {
    type: 'missing_required',
    shortLabel: 'Missing fields',
    message: `Missing: ${missing.join(', ')}.`,
    missing,
  };
}

export function checkNeedsReview(check) {
  if (check?.verified) return false;
  if (checkFieldFlag(check)) return true;
  if (checkMultiPidFlag(check)) return true;
  if (checkNameMismatchFlag(check)) return true;
  const pids = Array.isArray(check?.pids) && check.pids.length ? check.pids : [{ pid: '' }];
  return pids.some((entry) => Boolean(pidEntryFlag(entry)));
}

export function checkStatus(check) {
  if (check?.verified) return { key: 'verified', label: 'Verified' };
  if (checkNeedsReview(check)) return { key: 'needs_review', label: 'Needs review' };
  return { key: 'ok', label: 'OK' };
}

/**
 * Short issue labels for the selected-check issue strip (deduped, stable order).
 */
export function checkIssueShortLabels(check) {
  if (!check || check.verified || !checkNeedsReview(check)) return [];
  const labels = [];
  const seen = new Set();
  const push = (label) => {
    if (!label || seen.has(label)) return;
    seen.add(label);
    labels.push(label);
  };

  const fieldFlag = checkFieldFlag(check);
  if (fieldFlag) {
    for (const field of fieldFlag.missing || []) {
      if (field === 'amount') push('Missing amount');
      else if (field === 'check number') push('Missing check number');
      else if (field === 'provider') push('Missing provider');
      else if (field === 'provider length') push('Provider too long');
      else push(fieldFlag.shortLabel);
    }
  }

  const multiPidFlag = checkMultiPidFlag(check);
  if (multiPidFlag) push(multiPidFlag.shortLabel);

  const nameMismatchFlag = checkNameMismatchFlag(check);
  if (nameMismatchFlag) push(nameMismatchFlag.shortLabel);

  const pids = Array.isArray(check.pids) && check.pids.length ? check.pids : [{ pid: '' }];
  for (const entry of pids) {
    const flag = pidEntryFlag(entry);
    if (flag) push(flag.shortLabel);
  }
  return labels;
}

export function summarizeReview(checks) {
  const list = Array.isArray(checks) ? checks : [];
  let totalAmount = 0;
  let needsReview = 0;
  let pidCount = 0;
  for (const check of list) {
    const pids = Array.isArray(check?.pids) ? check.pids : [];
    pidCount += pids.filter((entry) => String(entry?.pid ?? '').trim()).length;
    const amountText = String(check?.amount ?? '')
      .replace(/\$/g, '')
      .replace(/,/g, '')
      .replace(/\s/g, '');
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
