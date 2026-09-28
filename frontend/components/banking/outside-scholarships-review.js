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

function checkLabel(check) {
  const index = check.check_index ?? '?';
  if (check.back_page) {
    return `Check ${index} · pages ${check.front_page}–${check.back_page}`;
  }
  return `Check ${index} · page ${check.front_page}, no back scanned`;
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
  const [zoom, setZoom] = useState(1);
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
        event.preventDefault();
        handleClose();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [handleClose]);

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
                          <td className="p-2 whitespace-nowrap">{checkLabel(check)}</td>
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
                <div className="flex items-center gap-2 border-b px-3 py-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="icon"
                    aria-label="Zoom out"
                    onClick={() => setZoom((value) => Math.max(0.5, Number((value - 0.25).toFixed(2))))}
                  >
                    <ZoomOut className="h-4 w-4" />
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="icon"
                    aria-label="Zoom in"
                    onClick={() => setZoom((value) => Math.min(3, Number((value + 0.25).toFixed(2))))}
                  >
                    <ZoomIn className="h-4 w-4" />
                  </Button>
                  <Button type="button" variant="outline" size="sm" onClick={() => setZoom(1)}>
                    Fit to width
                  </Button>
                  <span className="text-xs text-muted-foreground">{Math.round(zoom * 100)}%</span>
                </div>
                <div className="flex-1 overflow-auto p-3 space-y-4">
                  {selectedCheck ? (
                    <>
                      <div>
                        <p className="mb-2 text-sm font-medium">Front</p>
                        {selectedCheck.front_image ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            src={selectedCheck.front_image}
                            alt={`Front of check ${selectedCheck.check_index}`}
                            className="w-full h-auto border rounded"
                            style={{ transform: `scale(${zoom})`, transformOrigin: 'top left' }}
                          />
                        ) : (
                          <p className="text-sm text-muted-foreground">No front image.</p>
                        )}
                      </div>
                      <div>
                        <p className="mb-2 text-sm font-medium">Back</p>
                        {selectedCheck.back_image ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            src={selectedCheck.back_image}
                            alt={`Back of check ${selectedCheck.check_index}`}
                            className="w-full h-auto border rounded"
                            style={{ transform: `scale(${zoom})`, transformOrigin: 'top left' }}
                          />
                        ) : (
                          <p className="text-sm text-muted-foreground">No back was scanned for this check.</p>
                        )}
                      </div>
                    </>
                  ) : (
                    <p className="text-sm text-muted-foreground">Select a check to view its images.</p>
                  )}
                </div>
              </div>
            </ResizablePanel>
          </ResizablePanelGroup>
        </div>

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
