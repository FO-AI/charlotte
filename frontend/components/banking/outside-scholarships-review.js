'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  Loader2,
  Plus,
  RotateCcw,
  Search,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '@/components/ui/resizable';
import { APIClient } from '@/lib/api-client';
import { useAuth } from '@/lib/auth/auth-context-msal';
import {
  checkIssueShortLabels,
  checkNeedsReview,
  checkStatus,
  hasNonBlankBadPid,
  isWellFormedPid,
  missingRequiredFields,
  normalizePidDigits,
  pidEntryFlag,
  ALLOWED_AID_TERMS,
  DEFAULT_AID_TERM,
  DEFAULT_AID_YEAR,
  isAllowedAidTerm,
  PROVIDER_MAX_LENGTH,
  summarizeReview,
} from '@/components/banking/outside-scholarships-flags';

const FOCUS_INPUT =
  'w-full rounded-lg border border-[#B7D7ED] bg-white px-3 py-2.5 text-sm shadow-sm transition-colors placeholder:text-muted-foreground hover:border-[#4B9CD3]/80 focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-offset-2 focus-visible:outline-navy';

const ERROR_INPUT =
  'border-red-400 bg-red-50 hover:border-red-500 focus-visible:outline-red-700';

const READONLY_SURFACE =
  'w-full rounded-lg border border-[#B7D7ED]/80 bg-[#EDF5FB] px-3 py-2.5 text-sm min-h-[2.625rem] flex items-center text-navy';

const SECTION_CARD =
  'rounded-xl border border-[#B7D7ED] bg-white p-3.5 shadow-sm';

const LIGHTBOX_MIN_ZOOM = 1;
const LIGHTBOX_MAX_ZOOM = 4;
const LIGHTBOX_ZOOM_STEP = 0.25;

function CheckImageLightbox({ src, alt, onClose }) {
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const dragRef = useRef(null);
  const closeButtonRef = useRef(null);

  useEffect(() => {
    closeButtonRef.current?.focus();
  }, []);

  useEffect(() => {
    const onKeyDown = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        onClose();
      } else if (event.key === '+' || event.key === '=') {
        event.preventDefault();
        setZoom((value) => Math.min(LIGHTBOX_MAX_ZOOM, Number((value + LIGHTBOX_ZOOM_STEP).toFixed(2))));
      } else if (event.key === '-') {
        event.preventDefault();
        setZoom((value) => {
          const next = Math.max(LIGHTBOX_MIN_ZOOM, Number((value - LIGHTBOX_ZOOM_STEP).toFixed(2)));
          if (next <= 1) setOffset({ x: 0, y: 0 });
          return next;
        });
      } else if (event.key === '0') {
        event.preventDefault();
        setZoom(1);
        setOffset({ x: 0, y: 0 });
      }
    };
    window.addEventListener('keydown', onKeyDown, true);
    return () => window.removeEventListener('keydown', onKeyDown, true);
  }, [onClose]);

  const adjustZoom = (nextZoom, anchor = null) => {
    setZoom((prev) => {
      const clamped = Math.min(
        LIGHTBOX_MAX_ZOOM,
        Math.max(LIGHTBOX_MIN_ZOOM, Number(Number(nextZoom).toFixed(2)))
      );
      if (clamped <= 1) {
        setOffset({ x: 0, y: 0 });
        return 1;
      }
      if (anchor && prev > 0) {
        const ratio = clamped / prev;
        setOffset((current) => ({
          x: anchor.x - (anchor.x - current.x) * ratio,
          y: anchor.y - (anchor.y - current.y) * ratio,
        }));
      }
      return clamped;
    });
  };

  const onDoubleClick = (event) => {
    event.preventDefault();
    if (zoom > 1) {
      setZoom(1);
      setOffset({ x: 0, y: 0 });
      return;
    }
    const rect = event.currentTarget.getBoundingClientRect();
    const x = event.clientX - rect.left - rect.width / 2;
    const y = event.clientY - rect.top - rect.height / 2;
    setZoom(2);
    setOffset({ x: -x, y: -y });
  };

  const onWheel = (event) => {
    event.preventDefault();
    const rect = event.currentTarget.getBoundingClientRect();
    const anchor = {
      x: event.clientX - rect.left - rect.width / 2,
      y: event.clientY - rect.top - rect.height / 2,
    };
    const delta = event.deltaY < 0 ? LIGHTBOX_ZOOM_STEP : -LIGHTBOX_ZOOM_STEP;
    adjustZoom(zoom + delta, anchor);
  };

  const onPointerDown = (event) => {
    if (zoom <= 1) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originX: offset.x,
      originY: offset.y,
    };
  };

  const onPointerMove = (event) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    setOffset({
      x: drag.originX + (event.clientX - drag.startX),
      y: drag.originY + (event.clientY - drag.startY),
    });
  };

  const onPointerUp = (event) => {
    if (dragRef.current?.pointerId === event.pointerId) {
      dragRef.current = null;
    }
  };

  return (
    <div
      className="fixed inset-0 z-[60] flex flex-col bg-black/70"
      role="dialog"
      aria-modal="true"
      aria-label={alt}
      onClick={onClose}
    >
      <div
        className="flex items-center justify-between gap-3 px-4 py-3 text-white"
        onClick={(event) => event.stopPropagation()}
      >
        <p className="text-sm truncate">{alt}</p>
        <div className="flex items-center gap-2 shrink-0">
          <Button
            type="button"
            variant="secondary"
            size="icon"
            aria-label="Zoom out"
            onClick={() => adjustZoom(zoom - LIGHTBOX_ZOOM_STEP)}
          >
            <ZoomOut className="h-4 w-4" />
          </Button>
          <Button
            type="button"
            variant="secondary"
            size="icon"
            aria-label="Zoom in"
            onClick={() => adjustZoom(zoom + LIGHTBOX_ZOOM_STEP)}
          >
            <ZoomIn className="h-4 w-4" />
          </Button>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => {
              setZoom(1);
              setOffset({ x: 0, y: 0 });
            }}
          >
            Fit
          </Button>
          <span className="text-xs tabular-nums w-12 text-center">{Math.round(zoom * 100)}%</span>
          <Button ref={closeButtonRef} type="button" variant="secondary" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
      <div
        className={`flex-1 min-h-0 overflow-hidden flex items-center justify-center px-4 pb-4 ${
          zoom > 1 ? 'cursor-grab active:cursor-grabbing' : 'cursor-zoom-in'
        }`}
        onClick={(event) => event.stopPropagation()}
        onWheel={onWheel}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={src}
          alt={alt}
          draggable={false}
          onDoubleClick={onDoubleClick}
          className="max-h-full max-w-full object-contain select-none shadow-2xl rounded-sm bg-white"
          style={{
            transform: `translate(${offset.x}px, ${offset.y}px) scale(${zoom})`,
            transformOrigin: 'center center',
          }}
        />
      </div>
      <p className="sr-only">
        Double-click to zoom in or out. Scroll to zoom. Drag when zoomed. Press Escape to close.
      </p>
      <p className="px-4 pb-3 text-center text-xs text-white/80" aria-hidden="true">
        Double-click to zoom · Scroll to zoom · Drag when zoomed · Esc to close
      </p>
    </div>
  );
}

function CheckThumb({ src, alt, label, emptyLabel, onOpen }) {
  if (!src) {
    return (
      <div className={`${SECTION_CARD} bg-[#EDF5FB]/60`}>
        <p className="mb-2 text-base font-bold text-navy">{label}</p>
        <div className="flex min-h-[8rem] items-center justify-center rounded-lg border border-dashed border-[#B7D7ED] bg-white/70 px-3 py-6">
          <p className="text-sm text-muted-foreground text-center">{emptyLabel}</p>
        </div>
      </div>
    );
  }

  return (
    <div className={SECTION_CARD}>
      <p className="mb-2 text-base font-bold text-navy">{label}</p>
      <button
        type="button"
        className="group relative block w-full overflow-hidden rounded-lg border border-[#B7D7ED] bg-[#EDF5FB]/40 text-left transition-shadow hover:shadow-md focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-offset-2 focus-visible:outline-navy"
        onClick={() => onOpen({ src, alt })}
        aria-label={`Enlarge ${alt}`}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={src} alt={alt} className="w-full h-auto max-h-40 object-contain bg-white" />
        <span className="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-navy/80 to-transparent px-3 py-2.5 text-xs font-medium text-white">
          Click to enlarge
        </span>
      </button>
    </div>
  );
}

let pidKeySeq = 0;
function nextPidKey() {
  pidKeySeq += 1;
  return `pid-${pidKeySeq}`;
}

function blankPidEntry() {
  return { pid: '', _key: nextPidKey(), active_directory: { status: 'not_found', name: null } };
}

function cloneChecks(checks) {
  return (checks || []).map((check) => ({
    ...check,
    pids: checksPidsWithKeys(check.pids),
    verified: false,
    _editedFields: {},
  }));
}

function checksPidsWithKeys(pids) {
  if (!pids?.length) return [blankPidEntry()];
  return pids.map((entry) => {
    const pid = entry.pid ?? '';
    const digits = String(pid).replace(/\D/g, '');
    const status = entry.active_directory?.status;
    const lookedUp =
      entry._lookedUpFor ||
      (digits && (status === 'found' || status === 'not_found') ? digits : undefined);
    return {
      ...entry,
      _key: entry._key || nextPidKey(),
      _lookedUpFor: lookedUp,
      active_directory: entry.active_directory
        ? { ...entry.active_directory }
        : { status: 'not_found', name: null },
    };
  });
}

function pageHint(check) {
  if (check.back_page) return `pp. ${check.front_page}–${check.back_page}`;
  return `p. ${check.front_page}`;
}

function StatusListIcon({ check }) {
  const status = checkStatus(check);
  if (status.key === 'needs_review') {
    return (
      <span
        className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-red-100 text-red-700"
        title="Needs review"
      >
        <AlertCircle className="h-4 w-4" aria-hidden="true" />
        <span className="sr-only">Needs review</span>
      </span>
    );
  }
  if (status.key === 'verified') {
    return (
      <span
        className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-emerald-700"
        title="Verified"
      >
        <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
        <span className="sr-only">Verified</span>
      </span>
    );
  }
  return (
    <span
      className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-emerald-50 text-emerald-600"
      title="OK"
    >
      <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
      <span className="sr-only">OK</span>
    </span>
  );
}

function FlagChip({ flag, onRetry }) {
  if (!flag || flag.type === 'ad_looking_up') return null;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Tooltip>
        <TooltipTrigger asChild>
          <Badge variant="danger" className="gap-1 font-medium">
            <AlertCircle className="h-3 w-3" aria-hidden="true" />
            {flag.shortLabel}
          </Badge>
        </TooltipTrigger>
        <TooltipContent>{flag.message}</TooltipContent>
      </Tooltip>
      {flag.type === 'ad_lookup_failed' && onRetry ? (
        <Button type="button" size="sm" variant="outline" onClick={onRetry} aria-label="Retry lookup">
          <RotateCcw className="h-3.5 w-3.5" />
          Retry
        </Button>
      ) : null}
    </div>
  );
}

function EditedMarker({ show, original }) {
  if (!show) return null;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="ml-1 shrink-0 rounded-md bg-[#EDF5FB] px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[#2C5080] ring-1 ring-[#B7D7ED]">
          Edited
        </span>
      </TooltipTrigger>
      <TooltipContent>Extracted: {original || '(blank)'}</TooltipContent>
    </Tooltip>
  );
}

function FieldLabel({ children, invalid }) {
  return (
    <span className="mb-1.5 flex items-center gap-1.5 text-[0.95rem] font-bold tracking-tight text-navy">
      {children}
      {invalid ? <AlertCircle className="h-4 w-4 text-red-600" aria-hidden="true" /> : null}
    </span>
  );
}

export default function OutsideScholarshipsReview({ preview, onClose, returnFocusRef }) {
  const { getAuthHeaders } = useAuth();
  const apiClientRef = useRef(null);
  if (!apiClientRef.current) {
    apiClientRef.current = new APIClient(getAuthHeaders);
  }
  const apiClient = apiClientRef.current;

  const extractedRef = useRef(cloneChecks(preview?.checks || []));
  const [checks, setChecks] = useState(() => cloneChecks(preview?.checks || []));
  const checksRef = useRef(checks);
  checksRef.current = checks;
  const [aidYear, setAidYear] = useState(preview?.aid_year || DEFAULT_AID_YEAR);
  const [aidTerm, setAidTerm] = useState(preview?.aid_term || DEFAULT_AID_TERM);
  const [filter, setFilter] = useState(() => {
    const initial = cloneChecks(preview?.checks || []);
    return summarizeReview(initial).needsReview > 0 ? 'needs_review' : 'all';
  });
  const [selectedIndex, setSelectedIndex] = useState(() => {
    const initial = cloneChecks(preview?.checks || []);
    const firstNeeding = initial.findIndex((check) => checkNeedsReview(check));
    return firstNeeding >= 0 ? firstNeeding : 0;
  });
  const [lightbox, setLightbox] = useState(null);
  const [exporting, setExporting] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [successMessage, setSuccessMessage] = useState('');
  const [liveMessage, setLiveMessage] = useState('');
  const [dirty, setDirty] = useState(false);
  // Zoopable field edits stay local until Enter so Needs review / auto-advance do not fire mid-type.
  // Shape: { checkIndex, field: 'amount'|'check_number'|'provider'|'pid', pidKey?, value }
  const [fieldDraft, setFieldDraft] = useState(null);
  const lookupSeqRef = useRef({});
  const rowRefs = useRef({});
  // Tracks needs-review for the *same* check only — used so selecting another check
  // does not look like the previous one was resolved (false auto-advance).
  const prevNeedsReviewRef = useRef(null);

  const summary = useMemo(() => summarizeReview(checks), [checks]);
  const selectedCheck = checks[selectedIndex] || checks[0] || null;
  const selectedCheckId = selectedCheck?.check_index;

  const committedFieldValue = useCallback((check, field, pidKey) => {
    if (!check) return '';
    if (field === 'pid') {
      const entry = (check.pids || []).find((item) => item._key === pidKey);
      return String(entry?.pid ?? '');
    }
    if (field === 'amount') return String(check.amount ?? '');
    if (field === 'check_number') return String(check.check_number ?? '');
    if (field === 'provider') return String(check.provider ?? '');
    return '';
  }, []);

  const fieldDraftMatches = useCallback(
    (field, pidKey) => {
      if (!fieldDraft || fieldDraft.checkIndex !== selectedCheckId || fieldDraft.field !== field) {
        return false;
      }
      if (field === 'pid') return fieldDraft.pidKey === pidKey;
      return true;
    },
    [fieldDraft, selectedCheckId]
  );

  const fieldDraftDirty = useMemo(() => {
    if (!fieldDraft || fieldDraft.checkIndex !== selectedCheckId || !selectedCheck) return false;
    const committed = committedFieldValue(selectedCheck, fieldDraft.field, fieldDraft.pidKey);
    return fieldDraft.value !== committed;
  }, [fieldDraft, selectedCheckId, selectedCheck, committedFieldValue]);

  const fieldInputValue = useCallback(
    (field, pidKey) => {
      if (fieldDraftMatches(field, pidKey)) return fieldDraft.value;
      return committedFieldValue(selectedCheck, field, pidKey);
    },
    [fieldDraft, fieldDraftMatches, committedFieldValue, selectedCheck]
  );

  const selectedHasBadPid = useMemo(
    () => (selectedCheck ? hasNonBlankBadPid(selectedCheck) : false),
    [selectedCheck]
  );
  const anyCheckHasBadPid = useMemo(() => checks.some((check) => hasNonBlankBadPid(check)), [checks]);
  const exportBlockedByBadPid = anyCheckHasBadPid;
  const visibleChecks = useMemo(() => {
    if (filter === 'needs_review') {
      return checks.filter(
        (check) => checkNeedsReview(check) || check.check_index === selectedCheckId
      );
    }
    return checks;
  }, [checks, filter, selectedCheckId]);

  const issueLabels = useMemo(
    () => (selectedCheck ? checkIssueShortLabels(selectedCheck) : []),
    [selectedCheck]
  );
  const missingFields = useMemo(
    () => (selectedCheck && !selectedCheck.verified ? missingRequiredFields(selectedCheck) : []),
    [selectedCheck]
  );
  const originalSelected =
    extractedRef.current.find((item) => item.check_index === selectedCheckId) || {};

  useEffect(() => {
    if (!dirty) return undefined;
    const onBeforeUnload = (event) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, [dirty]);

  useEffect(() => {
    const previous = document.activeElement;
    const returnNode = returnFocusRef?.current;
    return () => {
      if (returnNode?.focus) {
        returnNode.focus();
      } else if (previous && typeof previous.focus === 'function') {
        previous.focus();
      }
    };
  }, [returnFocusRef]);

  const handleClose = useCallback(() => {
    if (exporting) return;
    if (dirty) {
      const confirmed = window.confirm(
        'Discard this review? The extracted data will be lost and the PDF must be uploaded again.'
      );
      if (!confirmed) return;
    }
    onClose();
  }, [dirty, exporting, onClose]);

  useEffect(() => {
    const onKeyDown = (event) => {
      if (event.key === 'Escape') {
        if (lightbox) return;
        event.preventDefault();
        handleClose();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [handleClose, lightbox]);

  const markDirty = useCallback(() => setDirty(true), []);

  const clearVerifiedOnEdit = useCallback((check) => {
    if (check.verified) {
      return { ...check, verified: false };
    }
    return check;
  }, []);

  const updateCheck = useCallback(
    (checkIndex, updater, options = {}) => {
      const clearVerified = options.clearVerified !== false;
      setChecks((prev) =>
        prev.map((check) => {
          if (check.check_index !== checkIndex) return check;
          const next = updater(check);
          if (next === check) return check;
          return clearVerified ? clearVerifiedOnEdit(next) : next;
        })
      );
      markDirty();
    },
    [clearVerifiedOnEdit, markDirty]
  );

  const selectCheckByAbsoluteIndex = useCallback((index) => {
    setFieldDraft(null);
    setSelectedIndex(index);
    const check = checksRef.current[index];
    if (check) {
      rowRefs.current[check.check_index]?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }, []);

  const goToNextNeedingReview = useCallback(() => {
    const list = checksRef.current;
    const start = selectedIndex;
    for (let offset = 1; offset <= list.length; offset += 1) {
      const index = (start + offset) % list.length;
      if (checkNeedsReview(list[index])) {
        selectCheckByAbsoluteIndex(index);
        return;
      }
    }
  }, [selectCheckByAbsoluteIndex, selectedIndex]);

  const revertFieldDraft = useCallback(() => {
    setFieldDraft(null);
  }, []);

  const beginFieldDraft = useCallback(
    (field, value, pidKey) => {
      if (!selectedCheck) return;
      setFieldDraft({
        checkIndex: selectedCheck.check_index,
        field,
        value,
        ...(field === 'pid' ? { pidKey } : {}),
      });
    },
    [selectedCheck]
  );

  /** Commit matching draft (if any). Returns the value now stored on the check for that field. */
  const commitFieldDraftFor = useCallback(
    (field, pidKey) => {
      if (!selectedCheck) return committedFieldValue(null, field, pidKey);
      const matches =
        fieldDraft &&
        fieldDraft.checkIndex === selectedCheck.check_index &&
        fieldDraft.field === field &&
        (field !== 'pid' || fieldDraft.pidKey === pidKey);

      if (!matches) {
        return committedFieldValue(selectedCheck, field, pidKey);
      }

      let committed = String(fieldDraft.value ?? '');
      if (field === 'amount' || field === 'check_number') {
        committed = committed.trim();
        updateCheck(selectedCheck.check_index, (current) => ({
          ...current,
          [field]: committed,
        }));
      } else if (field === 'provider') {
        committed = committed.trim().slice(0, PROVIDER_MAX_LENGTH);
        updateCheck(selectedCheck.check_index, (current) => ({
          ...current,
          provider: committed,
        }));
      } else if (field === 'pid') {
        committed = normalizePidDigits(committed).slice(0, 9);
        const previous = committedFieldValue(selectedCheck, 'pid', pidKey);
        // Only reset AD when the PID actually changes. Clearing AD on a no-op commit
        // races lookupPid's early-return (stale checksRef) and drops a good match.
        if (committed !== previous) {
          updateCheck(selectedCheck.check_index, (current) => {
            const next = [...(current.pids || [])];
            const idx = next.findIndex((item) => item._key === pidKey);
            if (idx < 0) return current;
            next[idx] = {
              ...next[idx],
              pid: committed,
              active_directory: { status: 'not_found', name: null },
              lookingUp: false,
              _lookedUpFor: undefined,
            };
            return { ...current, pids: next };
          });
        }
      }
      setFieldDraft(null);
      return committed;
    },
    [selectedCheck, fieldDraft, committedFieldValue, updateCheck]
  );

  // Drop an in-progress field draft when the selected check changes from elsewhere.
  useEffect(() => {
    setFieldDraft((prev) => {
      if (!prev || prev.checkIndex === selectedCheckId) return prev;
      return null;
    });
  }, [selectedCheckId]);

  // Auto-advance when the *currently selected* check stops needing review.
  useEffect(() => {
    if (!selectedCheck) {
      prevNeedsReviewRef.current = null;
      return;
    }
    // Hold auto-advance while a zoopable field is still being typed (uncommitted draft).
    if (fieldDraftDirty) {
      prevNeedsReviewRef.current = {
        checkIndex: selectedCheck.check_index,
        needs: checkNeedsReview(selectedCheck),
      };
      return;
    }
    const needs = checkNeedsReview(selectedCheck);
    const prev = prevNeedsReviewRef.current;
    const sameCheck = prev && prev.checkIndex === selectedCheck.check_index;
    if (sameCheck && prev.needs === true && needs === false) {
      const start = selectedIndex;
      let advanced = false;
      for (let offset = 1; offset <= checks.length; offset += 1) {
        const index = (start + offset) % checks.length;
        if (checkNeedsReview(checks[index])) {
          selectCheckByAbsoluteIndex(index);
          advanced = true;
          break;
        }
      }
      if (!advanced) {
        setLiveMessage('All checks reviewed. You can export Excel.');
      }
    }
    prevNeedsReviewRef.current = {
      checkIndex: selectedCheck.check_index,
      needs,
    };
  }, [checks, selectedCheck, selectedIndex, selectCheckByAbsoluteIndex, fieldDraftDirty]);

  const lookupPid = useCallback(
    async (checkIndex, pidKey, pidValue) => {
      const trimmed = String(pidValue ?? '').trim();
      const digits = normalizePidDigits(trimmed);
      const currentCheck = checksRef.current.find((check) => check.check_index === checkIndex);
      const currentEntry = (currentCheck?.pids || []).find((entry) => entry._key === pidKey);
      if (!currentEntry) return;

      if (!isWellFormedPid(trimmed)) {
        const samePid = String(currentEntry.pid ?? '') === trimmed;
        const alreadyClear =
          !currentEntry.lookingUp &&
          (currentEntry.active_directory?.status === 'not_found' || !currentEntry.active_directory) &&
          !currentEntry.active_directory?.name;
        if (samePid && alreadyClear) return;

        updateCheck(checkIndex, (check) => {
          const pids = [...(check.pids || [])];
          const idx = pids.findIndex((entry) => entry._key === pidKey);
          if (idx < 0) return check;
          pids[idx] = {
            ...pids[idx],
            pid: trimmed,
            active_directory: { status: 'not_found', name: null },
            lookingUp: false,
          };
          return { ...check, pids };
        });
        return;
      }

      const currentDigits = normalizePidDigits(currentEntry.pid);
      const adStatus = currentEntry.active_directory?.status;
      if (
        digits === currentDigits &&
        currentEntry._lookedUpFor === digits &&
        !currentEntry.lookingUp &&
        (adStatus === 'found' || adStatus === 'not_found')
      ) {
        if (String(currentEntry.pid ?? '') !== digits) {
          updateCheck(
            checkIndex,
            (check) => {
              const pids = [...(check.pids || [])];
              const idx = pids.findIndex((entry) => entry._key === pidKey);
              if (idx < 0) return check;
              pids[idx] = { ...pids[idx], pid: digits };
              return { ...check, pids };
            },
            { clearVerified: false }
          );
        }
        return;
      }

      const seqKey = `${checkIndex}:${pidKey}`;
      const seq = (lookupSeqRef.current[seqKey] || 0) + 1;
      lookupSeqRef.current[seqKey] = seq;

      updateCheck(
        checkIndex,
        (check) => {
          const pids = [...(check.pids || [])];
          const idx = pids.findIndex((entry) => entry._key === pidKey);
          if (idx < 0) return check;
          pids[idx] = { ...pids[idx], pid: digits, lookingUp: true };
          return { ...check, pids };
        },
        { clearVerified: false }
      );

      try {
        const result = await apiClient.lookupOutsideScholarshipActiveDirectoryNames([digits]);
        if (lookupSeqRef.current[seqKey] !== seq) return;
        const entry = (result.pids || []).find(
          (item) => normalizePidDigits(item.pid) === digits || item.pid === digits
        );
        const ad = entry?.active_directory || { status: 'not_found', name: null };
        updateCheck(
          checkIndex,
          (check) => {
            const pids = [...(check.pids || [])];
            const idx = pids.findIndex((item) => item._key === pidKey);
            if (idx < 0) return check;
            if (normalizePidDigits(pids[idx].pid) !== digits) return check;
            pids[idx] = {
              ...pids[idx],
              pid: digits,
              active_directory: ad,
              lookingUp: false,
              _lookedUpFor: digits,
            };
            return { ...check, pids };
          },
          { clearVerified: false }
        );
        if (ad.status === 'found') {
          setLiveMessage(`Name found: ${ad.name}`);
        } else if (ad.status === 'not_found') {
          setLiveMessage(`No Active Directory account has PID ${digits}`);
        } else {
          setLiveMessage("Couldn't reach Active Directory.");
        }
      } catch (error) {
        if (lookupSeqRef.current[seqKey] !== seq) return;
        updateCheck(
          checkIndex,
          (check) => {
            const pids = [...(check.pids || [])];
            const idx = pids.findIndex((item) => item._key === pidKey);
            if (idx < 0) return check;
            if (normalizePidDigits(pids[idx].pid) !== digits) return check;
            pids[idx] = {
              ...pids[idx],
              pid: digits,
              active_directory: { status: 'lookup_failed', name: null },
              lookingUp: false,
              _lookedUpFor: undefined,
            };
            return { ...check, pids };
          },
          { clearVerified: false }
        );
        setLiveMessage(error.message || "Couldn't reach Active Directory.");
      }
    },
    [apiClient, updateCheck]
  );

  const buildExportPayload = () => {
    const extracted = extractedRef.current;
    return {
      aid_year: aidYear,
      aid_term: aidTerm,
      checks: checks.map((check, index) => {
        const original = extracted[index] || extracted.find((item) => item.check_index === check.check_index) || {};
        return {
          check_index: check.check_index,
          extracted: {
            amount: original.amount,
            check_number: original.check_number,
            name: original.name,
            provider: original.provider,
            scholarship_name: original.scholarship_name,
            pids: (original.pids || []).map((entry) => ({
              pid: entry.pid,
              active_directory: entry.active_directory,
            })),
          },
          reviewed: {
            amount: check.amount,
            check_number: check.check_number,
            name: check.name,
            provider: check.provider,
            scholarship_name: check.scholarship_name,
            pids: (check.pids || []).map((entry) => ({
              pid: entry.pid,
              active_directory: entry.active_directory,
            })),
          },
          verified: Boolean(check.verified),
        };
      }),
    };
  };

  const handleExport = async () => {
    if (summary.needsReview > 0) return;
    const sanitizedAidYear = String(aidYear || '').trim();
    if (!/^\d{4}$/.test(sanitizedAidYear)) {
      setErrorMessage('Aid year must be a 4-digit year.');
      return;
    }
    if (!isAllowedAidTerm(aidTerm)) {
      setErrorMessage(`Aid term must be one of: ${ALLOWED_AID_TERMS.join(', ')}.`);
      return;
    }
    setExporting(true);
    setErrorMessage('');
    setSuccessMessage('');
    try {
      const { blob, filename } = await apiClient.exportOutsideScholarshipsExcel({
        ...buildExportPayload(),
        aid_year: sanitizedAidYear,
        aid_term: aidTerm,
      });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      setSuccessMessage('Excel exported.');
      setLiveMessage('Excel exported.');
      setDirty(false);
      onClose();
    } catch (error) {
      setErrorMessage(error.message || 'Export failed. Please try again.');
    } finally {
      setExporting(false);
    }
  };

  const toggleVerified = () => {
    if (!selectedCheck) return;
    setChecks((prev) =>
      prev.map((item) =>
        item.check_index === selectedCheck.check_index
          ? { ...item, verified: !item.verified }
          : item
      )
    );
    markDirty();
  };

  const amountInvalid = missingFields.includes('amount');
  const checkNumberInvalid = missingFields.includes('check number');
  const providerInvalid =
    missingFields.includes('provider') || missingFields.includes('provider length');

  return (
    <TooltipProvider>
      <div
        className="fixed inset-0 z-50 flex flex-col bg-[#F7FBFE]"
        role="dialog"
        aria-modal="true"
        aria-label="Review outside scholarship checks"
      >
        <div className="border-b border-[#B7D7ED] bg-white px-4 py-3.5 shadow-sm flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-wide text-[#4B9CD3]">
              Outside scholarships
            </p>
            <p className="mt-0.5 text-sm text-muted-foreground truncate">
              {preview?.filename || 'checks.pdf'}
            </p>
            <div className="mt-2.5 flex flex-wrap items-end gap-3">
              <label className="text-sm">
                <span className="block mb-1.5 text-[0.95rem] font-bold text-navy">Aid year</span>
                <Input
                  value={aidYear}
                  maxLength={4}
                  inputMode="numeric"
                  className={`${FOCUS_INPUT} w-28`}
                  onChange={(event) => {
                    setAidYear(event.target.value);
                    markDirty();
                  }}
                />
              </label>
              <label className="text-sm">
                <span className="block mb-1.5 text-[0.95rem] font-bold text-navy">Aid term</span>
                <select
                  value={aidTerm}
                  className={`${FOCUS_INPUT} w-28`}
                  onChange={(event) => {
                    setAidTerm(event.target.value);
                    markDirty();
                  }}
                >
                  {ALLOWED_AID_TERMS.map((term) => (
                    <option key={term} value={term}>
                      {term}
                    </option>
                  ))}
                </select>
              </label>
              <div
                className={`mb-0.5 flex items-center gap-2 rounded-full px-3 py-1.5 text-sm ${
                  summary.needsReview > 0
                    ? 'bg-red-50 text-red-950 ring-1 ring-red-200'
                    : 'bg-emerald-50 text-emerald-900 ring-1 ring-emerald-200'
                }`}
              >
                {summary.needsReview > 0 ? (
                  <AlertCircle className="h-4 w-4 text-red-600 shrink-0" aria-hidden="true" />
                ) : (
                  <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" aria-hidden="true" />
                )}
                <span className="font-semibold">
                  {summary.needsReview} of {summary.checkCount} left
                </span>
                <span className="text-muted-foreground font-normal">
                  · {summary.pidCount} PIDs · $
                  {summary.totalAmount.toLocaleString(undefined, {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                  })}
                </span>
              </div>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex rounded-lg border border-[#B7D7ED] bg-[#EDF5FB]/50 p-0.5 overflow-hidden">
              <Button
                type="button"
                variant={filter === 'all' ? 'default' : 'ghost'}
                size="sm"
                onClick={() => setFilter('all')}
              >
                All checks
              </Button>
              <Button
                type="button"
                variant={filter === 'needs_review' ? 'default' : 'ghost'}
                size="sm"
                onClick={() => setFilter('needs_review')}
              >
                Needs review
              </Button>
            </div>
            <Button type="button" variant="outline" size="sm" onClick={goToNextNeedingReview}>
              Next issue
              <ChevronDown className="h-4 w-4" aria-hidden="true" />
            </Button>
            <div className="flex items-center gap-2">
              <Button type="button" variant="outline" onClick={handleClose} disabled={exporting}>
                Cancel
              </Button>
              <div className="flex flex-col items-end gap-1">
                <Button
                  type="button"
                  onClick={handleExport}
                  disabled={exporting || summary.needsReview > 0 || exportBlockedByBadPid}
                >
                  {exporting ? 'Exporting…' : 'Export Excel'}
                </Button>
                {exportBlockedByBadPid ? (
                  <span className="text-xs text-red-700">Bad PID — fix or clear before export</span>
                ) : summary.needsReview > 0 ? (
                  <span className="text-xs text-muted-foreground">
                    {summary.needsReview} of {summary.checkCount} left
                  </span>
                ) : null}
              </div>
            </div>
          </div>
        </div>

        {(errorMessage || successMessage) && (
          <div className="px-4 pt-3">
            {errorMessage ? (
              <Alert className="border-red-200 bg-red-50">
                <AlertDescription className="text-red-800">{errorMessage}</AlertDescription>
              </Alert>
            ) : null}
            {successMessage ? (
              <Alert>
                <AlertDescription>{successMessage}</AlertDescription>
              </Alert>
            ) : null}
          </div>
        )}

        <div className="flex-1 min-h-0">
          <ResizablePanelGroup direction="horizontal" className="h-full">
            <ResizablePanel defaultSize={28} minSize={20} className="min-w-[12rem]">
              <div className="h-full overflow-auto border-r border-[#B7D7ED] bg-white">
                <div className="sticky top-0 z-10 border-b border-[#B7D7ED] bg-[#EDF5FB] px-3 py-2.5">
                  <p className="text-xs font-bold uppercase tracking-wide text-navy">Checks</p>
                </div>
                <ul className="p-2 space-y-1" role="listbox" aria-label="Checks">
                  {visibleChecks.map((check) => {
                    const absoluteIndex = checks.findIndex(
                      (item) => item.check_index === check.check_index
                    );
                    const selected = selectedCheckId === check.check_index;
                    const status = checkStatus(check);
                    return (
                      <li key={check.check_index}>
                        <button
                          type="button"
                          role="option"
                          aria-selected={selected}
                          ref={(node) => {
                            rowRefs.current[check.check_index] = node;
                          }}
                          className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2.5 text-left text-sm transition-colors focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-offset-[-3px] focus-visible:outline-navy ${
                            selected
                              ? 'bg-[rgba(75,156,211,0.18)] ring-1 ring-[#4B9CD3]/50 shadow-sm'
                              : 'hover:bg-[#EDF5FB]'
                          }`}
                          onClick={() => selectCheckByAbsoluteIndex(absoluteIndex)}
                        >
                          <StatusListIcon check={check} />
                          <span className="min-w-0 flex-1">
                            <span className="flex items-baseline gap-1.5">
                              <span className="font-semibold text-navy">Check {check.check_index}</span>
                              <span className="text-xs text-muted-foreground">{pageHint(check)}</span>
                            </span>
                            <span className="block truncate text-xs text-muted-foreground mt-0.5">
                              ${String(check.amount || '0')} · {check.name || 'No payee'}
                            </span>
                          </span>
                          <span className="sr-only">{status.label}</span>
                        </button>
                      </li>
                    );
                  })}
                  {!visibleChecks.length ? (
                    <li className="px-3 py-8 text-sm text-muted-foreground text-center">
                      No checks in this filter.
                    </li>
                  ) : null}
                </ul>
              </div>
            </ResizablePanel>

            <ResizableHandle withHandle />

            <ResizablePanel defaultSize={72} minSize={40}>
              <div className="h-full overflow-auto p-4 sm:p-5 space-y-4">
                {!selectedCheck ? (
                  <div className={`${SECTION_CARD} flex min-h-[12rem] items-center justify-center`}>
                    <p className="text-sm text-muted-foreground">Select a check to review.</p>
                  </div>
                ) : (
                  <>
                    {issueLabels.length > 0 ? (
                      <div
                        className="flex items-start gap-2.5 rounded-xl border border-red-200 bg-gradient-to-r from-red-50 to-white px-4 py-3 text-sm text-red-950 shadow-sm"
                        role="status"
                      >
                        <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-red-100">
                          <AlertCircle className="h-4 w-4 text-red-600" aria-hidden="true" />
                        </span>
                        <div className="min-w-0 pt-0.5">
                          <p className="text-xs font-bold uppercase tracking-wide text-red-700">
                            Needs review
                          </p>
                          <p className="font-semibold mt-0.5">{issueLabels.join(' · ')}</p>
                        </div>
                      </div>
                    ) : (
                      <div
                        className="flex items-center gap-2.5 rounded-xl border border-emerald-200 bg-gradient-to-r from-emerald-50 to-white px-4 py-3 text-sm text-emerald-950 shadow-sm"
                        role="status"
                      >
                        <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-emerald-100">
                          <CheckCircle2 className="h-4 w-4 text-emerald-600" aria-hidden="true" />
                        </span>
                        <p className="font-semibold">
                          {summary.needsReview > 0
                            ? 'No issues on this check'
                            : 'Looks good — ready to export'}
                        </p>
                      </div>
                    )}

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <CheckThumb
                        label="Front"
                        src={selectedCheck.front_image}
                        alt={`Front of check ${selectedCheck.check_index}`}
                        emptyLabel="No front image."
                        onOpen={setLightbox}
                      />
                      <CheckThumb
                        label="Back"
                        src={selectedCheck.back_image}
                        alt={`Back of check ${selectedCheck.check_index}`}
                        emptyLabel="No back was scanned for this check."
                        onOpen={setLightbox}
                      />
                    </div>

                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
                    <div className={`${SECTION_CARD} grid grid-cols-1 sm:grid-cols-2 gap-3 content-start`}>
                      <div className="sm:col-span-2 -mt-0.5 mb-0.5">
                        <h3 className="text-base font-bold text-navy">Check details</h3>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          Edit extracted fields as needed
                        </p>
                      </div>
                      <label className="sm:col-span-2">
                        <FieldLabel>Payee name</FieldLabel>
                        <div className="flex items-center gap-1">
                          <input
                            className={FOCUS_INPUT}
                            aria-label={`Payee name for check ${selectedCheck.check_index}`}
                            value={selectedCheck.name ?? ''}
                            onChange={(event) => {
                              const value = event.target.value;
                              updateCheck(selectedCheck.check_index, (current) => ({
                                ...current,
                                name: value,
                              }));
                            }}
                          />
                          <EditedMarker
                            show={String(selectedCheck.name ?? '') !== String(originalSelected.name ?? '')}
                            original={originalSelected.name}
                          />
                        </div>
                      </label>

                      <label>
                        <FieldLabel invalid={amountInvalid}>Amount</FieldLabel>
                        <div className="flex items-center gap-1">
                          <input
                            className={`${FOCUS_INPUT} ${amountInvalid ? ERROR_INPUT : ''}`}
                            aria-invalid={amountInvalid || undefined}
                            aria-label={`Amount for check ${selectedCheck.check_index}`}
                            value={fieldInputValue('amount')}
                            onChange={(event) => {
                              beginFieldDraft('amount', event.target.value);
                            }}
                            onKeyDown={(event) => {
                              if (event.key === 'Enter') {
                                event.preventDefault();
                                commitFieldDraftFor('amount');
                                return;
                              }
                              if (event.key === 'Escape' && fieldDraftMatches('amount')) {
                                event.preventDefault();
                                event.stopPropagation();
                                revertFieldDraft();
                              }
                            }}
                            onBlur={() => {
                              if (fieldDraftMatches('amount')) revertFieldDraft();
                            }}
                          />
                          <EditedMarker
                            show={
                              String(selectedCheck.amount ?? '') !== String(originalSelected.amount ?? '')
                            }
                            original={originalSelected.amount}
                          />
                        </div>
                      </label>

                      <label>
                        <FieldLabel invalid={checkNumberInvalid}>Check number</FieldLabel>
                        <div className="flex items-center gap-1">
                          <input
                            className={`${FOCUS_INPUT} ${checkNumberInvalid ? ERROR_INPUT : ''}`}
                            aria-invalid={checkNumberInvalid || undefined}
                            aria-label={`Check number for check ${selectedCheck.check_index}`}
                            value={fieldInputValue('check_number')}
                            onChange={(event) => {
                              beginFieldDraft('check_number', event.target.value);
                            }}
                            onKeyDown={(event) => {
                              if (event.key === 'Enter') {
                                event.preventDefault();
                                commitFieldDraftFor('check_number');
                                return;
                              }
                              if (event.key === 'Escape' && fieldDraftMatches('check_number')) {
                                event.preventDefault();
                                event.stopPropagation();
                                revertFieldDraft();
                              }
                            }}
                            onBlur={() => {
                              if (fieldDraftMatches('check_number')) revertFieldDraft();
                            }}
                          />
                          <EditedMarker
                            show={
                              String(selectedCheck.check_number ?? '') !==
                              String(originalSelected.check_number ?? '')
                            }
                            original={originalSelected.check_number}
                          />
                        </div>
                      </label>

                      <label>
                        <FieldLabel invalid={providerInvalid}>Provider</FieldLabel>
                        <div className="flex items-center gap-1">
                          <input
                            className={`${FOCUS_INPUT} ${providerInvalid ? ERROR_INPUT : ''}`}
                            aria-invalid={providerInvalid || undefined}
                            aria-label={`Provider for check ${selectedCheck.check_index}`}
                            maxLength={PROVIDER_MAX_LENGTH}
                            value={fieldInputValue('provider')}
                            onChange={(event) => {
                              beginFieldDraft(
                                'provider',
                                event.target.value.slice(0, PROVIDER_MAX_LENGTH)
                              );
                            }}
                            onKeyDown={(event) => {
                              if (event.key === 'Enter') {
                                event.preventDefault();
                                commitFieldDraftFor('provider');
                                return;
                              }
                              if (event.key === 'Escape' && fieldDraftMatches('provider')) {
                                event.preventDefault();
                                event.stopPropagation();
                                revertFieldDraft();
                              }
                            }}
                            onBlur={() => {
                              if (fieldDraftMatches('provider')) revertFieldDraft();
                            }}
                          />
                          <EditedMarker
                            show={
                              String(selectedCheck.provider ?? '') !==
                              String(originalSelected.provider ?? '')
                            }
                            original={originalSelected.provider}
                          />
                        </div>
                      </label>

                      <label>
                        <FieldLabel>Scholarship name</FieldLabel>
                        <div className="flex items-center gap-1">
                          <input
                            className={FOCUS_INPUT}
                            aria-label={`Scholarship name for check ${selectedCheck.check_index}`}
                            value={selectedCheck.scholarship_name ?? ''}
                            onChange={(event) => {
                              const value = event.target.value;
                              updateCheck(selectedCheck.check_index, (current) => ({
                                ...current,
                                scholarship_name: value,
                              }));
                            }}
                          />
                          <EditedMarker
                            show={
                              String(selectedCheck.scholarship_name ?? '') !==
                              String(originalSelected.scholarship_name ?? '')
                            }
                            original={originalSelected.scholarship_name}
                          />
                        </div>
                      </label>
                    </div>

                    <div className={`${SECTION_CARD} space-y-3 h-full`}>
                      <div className="flex items-center justify-between gap-2">
                        <div>
                          <h3 className="text-base font-bold text-navy">PIDs</h3>
                          <p className="text-xs text-muted-foreground mt-0.5">
                            Look up each PID in Active Directory
                          </p>
                        </div>
                        {checkNeedsReview(selectedCheck) || selectedCheck.verified ? (
                          <div className="flex flex-col items-end gap-1">
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              onClick={toggleVerified}
                              disabled={!selectedCheck.verified && selectedHasBadPid}
                            >
                              {selectedCheck.verified ? 'Undo' : 'Mark verified'}
                            </Button>
                            {!selectedCheck.verified && selectedHasBadPid ? (
                              <span className="text-xs text-red-700">Bad PID</span>
                            ) : null}
                          </div>
                        ) : null}
                      </div>

                      <div className="space-y-3">
                        {selectedCheck.pids.map((entry, pidIndex) => {
                          const flag = pidEntryFlag(entry);
                          const pidInvalid = Boolean(flag) && flag.type !== 'ad_looking_up';
                          const extractedPid = (originalSelected.pids || [])[pidIndex]?.pid;
                          const pidKey = entry._key;
                          const adFound = entry.active_directory?.status === 'found';
                          // While rewriting a PID, hide the prior AD match until Enter/Search commits.
                          const pidDraftDiffers =
                            fieldDraftMatches('pid', pidKey) &&
                            fieldInputValue('pid', pidKey) !== String(entry.pid ?? '');
                          return (
                            <div
                              key={pidKey}
                              className={`rounded-xl border p-3.5 space-y-2.5 shadow-sm ${
                                pidInvalid
                                  ? 'border-red-300 bg-red-50/40'
                                  : 'border-[#B7D7ED] bg-[#EDF5FB]/35'
                              }`}
                            >
                              <div className="space-y-2.5">
                                <div>
                                  <FieldLabel invalid={pidInvalid}>PID</FieldLabel>
                                  <div className="flex items-center gap-1.5">
                                    <label className="sr-only" htmlFor={`pid-${pidKey}`}>
                                      PID for check {selectedCheck.check_index}
                                    </label>
                                    <input
                                      id={`pid-${pidKey}`}
                                      className={`${FOCUS_INPUT} ${pidInvalid ? ERROR_INPUT : ''}`}
                                      aria-invalid={pidInvalid || undefined}
                                      inputMode="numeric"
                                      maxLength={9}
                                      value={fieldInputValue('pid', pidKey)}
                                      onChange={(event) => {
                                        const value = normalizePidDigits(event.target.value).slice(
                                          0,
                                          9
                                        );
                                        beginFieldDraft('pid', value, pidKey);
                                      }}
                                      onKeyDown={(event) => {
                                        if (event.key === 'Enter') {
                                          event.preventDefault();
                                          const committed = commitFieldDraftFor('pid', pidKey);
                                          lookupPid(
                                            selectedCheck.check_index,
                                            pidKey,
                                            committed
                                          );
                                          return;
                                        }
                                        if (event.key === 'Escape' && fieldDraftMatches('pid', pidKey)) {
                                          event.preventDefault();
                                          event.stopPropagation();
                                          revertFieldDraft();
                                        }
                                      }}
                                      onBlur={() => {
                                        if (fieldDraftMatches('pid', pidKey)) revertFieldDraft();
                                      }}
                                    />
                                    <Button
                                      type="button"
                                      variant="outline"
                                      size="icon"
                                      className="shrink-0 h-[2.625rem] w-[2.625rem] border-[#B7D7ED] bg-white hover:bg-[#EDF5FB]"
                                      disabled={entry.lookingUp}
                                      aria-label={`Search Active Directory for PID on check ${selectedCheck.check_index}`}
                                      onMouseDown={(event) => {
                                        // Keep PID focus so blur does not discard an uncommitted draft.
                                        event.preventDefault();
                                      }}
                                      onClick={() => {
                                        const committed = commitFieldDraftFor('pid', pidKey);
                                        lookupPid(selectedCheck.check_index, pidKey, committed);
                                      }}
                                    >
                                      {entry.lookingUp ? (
                                        <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" />
                                      ) : (
                                        <Search className="h-4 w-4" />
                                      )}
                                    </Button>
                                    <EditedMarker
                                      show={String(entry.pid ?? '') !== String(extractedPid ?? '')}
                                      original={extractedPid}
                                    />
                                  </div>
                                </div>
                                <div>
                                  <FieldLabel>Active Directory name</FieldLabel>
                                  <div
                                    className={`${READONLY_SURFACE} ${
                                      adFound ? 'font-medium' : 'text-muted-foreground'
                                    }`}
                                    aria-live="polite"
                                  >
                                    {entry.lookingUp
                                      ? 'Looking up…'
                                      : !pidDraftDiffers && adFound
                                        ? entry.active_directory.name
                                        : '—'}
                                  </div>
                                </div>
                              </div>
                              <div className="flex flex-wrap items-center gap-2">
                                <FlagChip
                                  flag={flag}
                                  onRetry={
                                    flag?.type === 'ad_lookup_failed'
                                      ? () => lookupPid(selectedCheck.check_index, pidKey, entry.pid)
                                      : undefined
                                  }
                                />
                                {selectedCheck.pids.length > 1 ? (
                                  <Button
                                    type="button"
                                    variant="ghost"
                                    size="sm"
                                    className="text-muted-foreground h-auto px-1.5 py-0.5"
                                    aria-label={`Remove PID ${pidIndex + 1} from check ${selectedCheck.check_index}`}
                                    onClick={() => {
                                      updateCheck(selectedCheck.check_index, (current) => {
                                        const next = current.pids.filter((item) => item._key !== pidKey);
                                        return {
                                          ...current,
                                          pids: next.length ? next : [blankPidEntry()],
                                        };
                                      });
                                    }}
                                  >
                                    Remove
                                  </Button>
                                ) : null}
                              </div>
                            </div>
                          );
                        })}
                      </div>

                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="border-[#B7D7ED] bg-white hover:bg-[#EDF5FB]"
                        onClick={() => {
                          updateCheck(selectedCheck.check_index, (current) => ({
                            ...current,
                            pids: [...current.pids, blankPidEntry()],
                          }));
                        }}
                      >
                        <Plus className="h-4 w-4" />
                        Add PID
                      </Button>
                    </div>
                    </div>
                  </>
                )}
              </div>
            </ResizablePanel>
          </ResizablePanelGroup>
        </div>

        {lightbox ? (
          <CheckImageLightbox
            src={lightbox.src}
            alt={lightbox.alt}
            onClose={() => setLightbox(null)}
          />
        ) : null}

        <div className="sr-only" aria-live="polite">
          {liveMessage}
        </div>
        {exporting ? (
          <div className="absolute inset-0 bg-black/20 flex items-center justify-center" aria-hidden="true">
            <Loader2 className="h-8 w-8 animate-spin text-navy motion-reduce:animate-none" />
          </div>
        ) : null}
      </div>
    </TooltipProvider>
  );
}
