'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  Loader2,
  Minus,
  Plus,
  RotateCcw,
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
  checkFieldFlag,
  checkNeedsReview,
  checkStatus,
  isWellFormedPid,
  pidEntryFlag,
  summarizeReview,
} from '@/components/banking/outside-scholarships-flags';

const FOCUS_INPUT =
  'w-full rounded-md border px-2 py-1.5 text-sm focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-offset-2 focus-visible:outline-navy';

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
      <div>
        <p className="mb-2 text-sm font-medium">{label}</p>
        <p className="text-sm text-muted-foreground">{emptyLabel}</p>
      </div>
    );
  }

  return (
    <div>
      <p className="mb-2 text-sm font-medium">{label}</p>
      <button
        type="button"
        className="group relative block w-full overflow-hidden rounded border bg-muted/20 text-left focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-offset-2 focus-visible:outline-navy"
        onClick={() => onOpen({ src, alt })}
        aria-label={`Enlarge ${alt}`}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={src} alt={alt} className="w-full h-auto" />
        <span className="pointer-events-none absolute inset-x-0 bottom-0 bg-black/55 px-2 py-1.5 text-xs text-white opacity-90 group-hover:opacity-100">
          Click to enlarge · double-click zooms
        </span>
      </button>
    </div>
  );
}

function cloneChecks(checks) {
  return (checks || []).map((check) => ({
    ...check,
    pids: (check.pids || []).map((entry) => ({
      ...entry,
      active_directory: entry.active_directory ? { ...entry.active_directory } : { status: 'not_found', name: null },
    })),
    verified: false,
    _editedFields: {},
  }));
}

function CheckLabel({ check }) {
  const index = check.check_index ?? '?';
  const pages = check.back_page
    ? `Pages ${check.front_page}–${check.back_page}`
    : `Page ${check.front_page}, no back`;
  return (
    <div className="leading-tight">
      <div className="font-medium">Check {index}</div>
      <div className="text-xs text-muted-foreground whitespace-normal">{pages}</div>
    </div>
  );
}

function StatusBadge({ check }) {
  const status = checkStatus(check);
  if (status.key === 'needs_review') {
    return (
      <Badge variant="warning" className="gap-1">
        <AlertCircle className="h-3.5 w-3.5" aria-hidden="true" />
        Needs review
      </Badge>
    );
  }
  if (status.key === 'verified') {
    return (
      <Badge variant="success" className="gap-1">
        <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
        Verified
      </Badge>
    );
  }
  return (
    <Badge variant="secondary" className="gap-1">
      <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
      OK
    </Badge>
  );
}

function EditedMarker({ show, original }) {
  if (!show) return null;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="ml-1 text-[10px] uppercase tracking-wide text-[#2C5080]">Edited</span>
      </TooltipTrigger>
      <TooltipContent>Extracted: {original || '(blank)'}</TooltipContent>
    </Tooltip>
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
  const [aidYear, setAidYear] = useState(preview?.aid_year || String(new Date().getFullYear()));
  const [aidTerm, setAidTerm] = useState(preview?.aid_term || 'F');
  const [filter, setFilter] = useState('all');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [lightbox, setLightbox] = useState(null);
  const [exporting, setExporting] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [successMessage, setSuccessMessage] = useState('');
  const [liveMessage, setLiveMessage] = useState('');
  const [dirty, setDirty] = useState(false);
  const lookupSeqRef = useRef({});
  const rowRefs = useRef({});

  const summary = useMemo(() => summarizeReview(checks), [checks]);
  const visibleChecks = useMemo(() => {
    if (filter === 'needs_review') {
      return checks.filter((check) => checkNeedsReview(check));
    }
    return checks;
  }, [checks, filter]);

  const selectedCheck = checks[selectedIndex] || checks[0] || null;

  useEffect(() => {
    const onBeforeUnload = (event) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, []);

  useEffect(() => {
    const previous = document.activeElement;
    return () => {
      if (returnFocusRef?.current?.focus) {
        returnFocusRef.current.focus();
      } else if (previous && previous.focus) {
        previous.focus();
      }
    };
  }, [returnFocusRef]);

  const handleClose = useCallback(() => {
    if (dirty || exporting) {
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
          return clearVerified ? clearVerifiedOnEdit(next) : next;
        })
      );
      markDirty();
    },
    [clearVerifiedOnEdit, markDirty]
  );

  const lookupPid = useCallback(
    async (checkIndex, pidIndex, pidValue) => {
      const trimmed = String(pidValue ?? '').trim();
      if (!isWellFormedPid(trimmed)) {
        updateCheck(checkIndex, (check) => {
          const pids = [...(check.pids || [])];
          pids[pidIndex] = {
            ...pids[pidIndex],
            pid: trimmed,
            active_directory: { status: 'not_found', name: null },
            lookingUp: false,
          };
          return { ...check, pids };
        });
        return;
      }

      const key = `${checkIndex}:${pidIndex}`;
      const seq = (lookupSeqRef.current[key] || 0) + 1;
      lookupSeqRef.current[key] = seq;

      // Lookup status updates are not field edits — do not clear verified.
      updateCheck(
        checkIndex,
        (check) => {
          const pids = [...(check.pids || [])];
          pids[pidIndex] = { ...pids[pidIndex], pid: trimmed, lookingUp: true };
          return { ...check, pids };
        },
        { clearVerified: false }
      );

      try {
        const result = await apiClient.lookupOutsideScholarshipActiveDirectoryNames([trimmed]);
        if (lookupSeqRef.current[key] !== seq) return;
        const entry = (result.pids || []).find((item) => item.pid === trimmed);
        const ad = entry?.active_directory || { status: 'not_found', name: null };
        updateCheck(
          checkIndex,
          (check) => {
            const pids = [...(check.pids || [])];
            pids[pidIndex] = { ...pids[pidIndex], pid: trimmed, active_directory: ad, lookingUp: false };
            return { ...check, pids };
          },
          { clearVerified: false }
        );
        if (ad.status === 'found') {
          setLiveMessage(`Name found: ${ad.name}`);
        } else if (ad.status === 'not_found') {
          setLiveMessage(`No Active Directory account has PID ${trimmed}`);
        } else {
          setLiveMessage("Couldn't reach Active Directory.");
        }
      } catch (error) {
        if (lookupSeqRef.current[key] !== seq) return;
        updateCheck(
          checkIndex,
          (check) => {
            const pids = [...(check.pids || [])];
            pids[pidIndex] = {
              ...pids[pidIndex],
              pid: trimmed,
              active_directory: { status: 'lookup_failed', name: null },
              lookingUp: false,
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

  const goToNextNeedingReview = () => {
    const start = selectedIndex;
    for (let offset = 1; offset <= checks.length; offset += 1) {
      const index = (start + offset) % checks.length;
      if (checkNeedsReview(checks[index])) {
        setSelectedIndex(index);
        rowRefs.current[checks[index].check_index]?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        return;
      }
    }
  };

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
    setExporting(true);
    setErrorMessage('');
    setSuccessMessage('');
    try {
      const { blob, filename } = await apiClient.exportOutsideScholarshipsExcel(buildExportPayload());
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

  const ensurePidList = (check) => {
    if (Array.isArray(check.pids) && check.pids.length) return check.pids;
    return [{ pid: '', active_directory: { status: 'not_found', name: null } }];
  };

  return (
    <TooltipProvider>
      <div
        className="fixed inset-0 z-50 flex flex-col bg-background"
        role="dialog"
        aria-modal="true"
        aria-label="Review outside scholarship checks"
      >
        <div className="border-b px-4 py-3 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0">
            <p className="text-sm text-muted-foreground truncate">{preview?.filename || 'checks.pdf'}</p>
            <div className="mt-2 flex flex-wrap items-end gap-3">
              <label className="text-sm">
                <span className="block mb-1 font-medium">Aid year</span>
                <Input
                  value={aidYear}
                  maxLength={4}
                  inputMode="numeric"
                  className={FOCUS_INPUT}
                  onChange={(event) => {
                    setAidYear(event.target.value);
                    markDirty();
                  }}
                />
              </label>
              <label className="text-sm">
                <span className="block mb-1 font-medium">Aid term</span>
                <select
                  value={aidTerm}
                  className={FOCUS_INPUT + ' bg-background'}
                  onChange={(event) => {
                    setAidTerm(event.target.value);
                    markDirty();
                  }}
                >
                  <option value="F">F</option>
                  <option value="S">S</option>
                </select>
              </label>
              <p className="text-sm text-muted-foreground pb-2">
                {summary.checkCount} checks · {summary.pidCount} PIDs · $
                {summary.totalAmount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ·{' '}
                <span className="font-medium text-foreground">{summary.needsReview} checks need review</span>
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex rounded-md border overflow-hidden">
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
              Next check needing review
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
                  disabled={exporting || summary.needsReview > 0}
                >
                  {exporting ? 'Exporting…' : 'Export Excel'}
                </Button>
                {summary.needsReview > 0 ? (
                  <span className="text-xs text-muted-foreground">{summary.needsReview} checks need review</span>
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
            <ResizablePanel defaultSize={62} minSize={40}>
              <div className="h-full overflow-auto p-4">
                <table className="w-full min-w-[960px] border-collapse text-sm">
                  <thead className="sticky top-0 bg-background z-10">
                    <tr className="border-b text-left">
                      <th className="p-2 font-medium">Status</th>
                      <th className="p-2 font-medium">Check</th>
                      <th className="p-2 font-medium">PIDs</th>
                      <th className="p-2 font-medium">Payee name</th>
                      <th className="p-2 font-medium">Amount</th>
                      <th className="p-2 font-medium">Check number</th>
                      <th className="p-2 font-medium">Provider</th>
                      <th className="p-2 font-medium">Scholarship name</th>
                      <th className="p-2 font-medium">Verified</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleChecks.map((check) => {
                      const absoluteIndex = checks.findIndex((item) => item.check_index === check.check_index);
                      const original = extractedRef.current.find((item) => item.check_index === check.check_index) || {};
                      const pids = ensurePidList(check);
                      const fieldFlag = checkFieldFlag(check);
                      const selected = selectedCheck?.check_index === check.check_index;
                      return (
                        <tr
                          key={check.check_index}
                          ref={(node) => {
                            rowRefs.current[check.check_index] = node;
                          }}
                          className={`border-b align-top ${selected ? 'bg-[rgba(75,156,211,0.08)]' : ''}`}
                          onFocusCapture={() => setSelectedIndex(absoluteIndex)}
                          onClick={() => setSelectedIndex(absoluteIndex)}
                        >
                          <td className="p-2">
                            <StatusBadge check={check} />
                            {fieldFlag ? <p className="mt-1 text-xs text-amber-900">{fieldFlag.message}</p> : null}
                          </td>
                          <td className="p-2 w-[5.5rem] max-w-[5.5rem]"><CheckLabel check={check} /></td>
                          <td className="p-2 min-w-[220px]">
                            <div className="space-y-2">
                              {pids.map((entry, pidIndex) => {
                                const flag = pidEntryFlag(entry);
                                const extractedPid = (original.pids || [])[pidIndex]?.pid;
                                return (
                                  <div key={`${check.check_index}-${pidIndex}`} className="rounded border p-2 space-y-1">
                                    <div className="flex items-center gap-2">
                                      <label className="sr-only" htmlFor={`pid-${check.check_index}-${pidIndex}`}>
                                        PID for check {check.check_index}
                                      </label>
                                      <input
                                        id={`pid-${check.check_index}-${pidIndex}`}
                                        className={FOCUS_INPUT}
                                        value={entry.pid ?? ''}
                                        onChange={(event) => {
                                          const value = event.target.value;
                                          updateCheck(check.check_index, (current) => {
                                            const next = [...ensurePidList(current)];
                                            next[pidIndex] = {
                                              ...next[pidIndex],
                                              pid: value,
                                              active_directory: next[pidIndex]?.active_directory || {
                                                status: 'not_found',
                                                name: null,
                                              },
                                            };
                                            return { ...current, pids: next };
                                          });
                                        }}
                                        onBlur={(event) => lookupPid(check.check_index, pidIndex, event.target.value)}
                                        onKeyDown={(event) => {
                                          if (event.key === 'Enter') {
                                            event.preventDefault();
                                            lookupPid(check.check_index, pidIndex, event.currentTarget.value);
                                          }
                                        }}
                                      />
                                      <EditedMarker show={String(entry.pid ?? '') !== String(extractedPid ?? '')} original={extractedPid} />
                                      <Button
                                        type="button"
                                        variant="ghost"
                                        size="icon"
                                        aria-label={`Remove PID ${pidIndex + 1} from check ${check.check_index}`}
                                        onClick={() => {
                                          updateCheck(check.check_index, (current) => {
                                            const next = ensurePidList(current).filter((_, index) => index !== pidIndex);
                                            return { ...current, pids: next.length ? next : [] };
                                          });
                                        }}
                                      >
                                        <Minus className="h-4 w-4" />
                                      </Button>
                                    </div>
                                    <p className="text-xs text-muted-foreground min-h-[1rem]">
                                      {entry.lookingUp
                                        ? 'Looking up…'
                                        : entry.active_directory?.status === 'found'
                                          ? entry.active_directory.name
                                          : ''}
                                    </p>
                                    {flag ? (
                                      <div className="flex items-center gap-2 text-xs text-amber-900">
                                        <span>{flag.message}</span>
                                        {flag.type === 'ad_lookup_failed' ? (
                                          <Button
                                            type="button"
                                            size="sm"
                                            variant="outline"
                                            aria-label={`Retry lookup for PID ${entry.pid || ''}`}
                                            onClick={() => lookupPid(check.check_index, pidIndex, entry.pid)}
                                          >
                                            <RotateCcw className="h-3.5 w-3.5" />
                                            Retry lookup
                                          </Button>
                                        ) : null}
                                      </div>
                                    ) : null}
                                  </div>
                                );
                              })}
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={() => {
                                  updateCheck(check.check_index, (current) => ({
                                    ...current,
                                    pids: [
                                      ...ensurePidList(current),
                                      { pid: '', active_directory: { status: 'not_found', name: null } },
                                    ],
                                  }));
                                }}
                              >
                                <Plus className="h-4 w-4" />
                                Add PID
                              </Button>
                            </div>
                          </td>
                          {[
                            ['name', 'Payee name'],
                            ['amount', 'Amount'],
                            ['check_number', 'Check number'],
                            ['provider', 'Provider'],
                            ['scholarship_name', 'Scholarship name'],
                          ].map(([field]) => (
                            <td key={field} className="p-2 min-w-[120px]">
                              <div className="flex items-center gap-1">
                                <input
                                  className={FOCUS_INPUT}
                                  aria-label={`${field.replace('_', ' ')} for check ${check.check_index}`}
                                  value={check[field] ?? ''}
                                  onChange={(event) => {
                                    const value = event.target.value;
                                    updateCheck(check.check_index, (current) => ({ ...current, [field]: value }));
                                  }}
                                />
                                <EditedMarker
                                  show={String(check[field] ?? '') !== String(original[field] ?? '')}
                                  original={original[field]}
                                />
                              </div>
                            </td>
                          ))}
                          <td className="p-2">
                            {checkNeedsReview(check) || check.verified ? (
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={() => {
                                  setChecks((prev) =>
                                    prev.map((item) =>
                                      item.check_index === check.check_index
                                        ? { ...item, verified: !item.verified }
                                        : item
                                    )
                                  );
                                  markDirty();
                                }}
                              >
                                {check.verified ? 'Undo' : 'Mark verified'}
                              </Button>
                            ) : (
                              <span className="text-xs text-muted-foreground">—</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </ResizablePanel>
            <ResizableHandle withHandle />
            <ResizablePanel defaultSize={38} minSize={24}>
              <div className="h-full flex flex-col border-l">
                <div className="border-b px-3 py-2">
                  <p className="text-sm font-medium">Check images</p>
                  <p className="text-xs text-muted-foreground">Click an image to open it full-size.</p>
                </div>
                <div className="flex-1 overflow-auto p-3 space-y-4">
                  {selectedCheck ? (
                    <>
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
                    </>
                  ) : (
                    <p className="text-sm text-muted-foreground">Select a check to view its images.</p>
                  )}
                </div>
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
