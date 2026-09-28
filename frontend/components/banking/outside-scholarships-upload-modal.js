'use client';

import { useRef, useState } from 'react';
import { X, FileCheck, FileText } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { APIClient } from '@/lib/api-client';
import { useAuth } from '@/lib/auth/auth-context-msal';
import OutsideScholarshipsReview from '@/components/banking/outside-scholarships-review';

const MAX_FILE_SIZE = 50 * 1024 * 1024;

function formatFileSize(bytes) {
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(0)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function OutsideScholarshipsUploadModal({ isOpen, onClose, returnFocusRef }) {
  const { getAuthHeaders } = useAuth();
  const apiClientRef = useRef(null);
  if (!apiClientRef.current) {
    apiClientRef.current = new APIClient(getAuthHeaders);
  }
  const apiClient = apiClientRef.current;
  const defaultAidYear = String(new Date().getFullYear());
  const [phase, setPhase] = useState('idle');
  const [selectedFile, setSelectedFile] = useState(null);
  const [aidYear, setAidYear] = useState(defaultAidYear);
  const [aidTerm, setAidTerm] = useState('F');
  const [errorMessage, setErrorMessage] = useState('');
  const [preview, setPreview] = useState(null);
  const fileInputRef = useRef(null);
  const localTriggerRef = useRef(null);
  const triggerRef = returnFocusRef || localTriggerRef;

  const extracting = phase === 'extracting';
  const reviewing = phase === 'review';

  const resetState = () => {
    setPhase('idle');
    setSelectedFile(null);
    setAidYear(defaultAidYear);
    setAidTerm('F');
    setErrorMessage('');
    setPreview(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleClose = () => {
    if (extracting) return;
    resetState();
    onClose();
  };

  const handleFileSelect = (files) => {
    if (!files || files.length === 0) return;
    setErrorMessage('');

    const file = files[0];
    const fileExtension = '.' + file.name.split('.').pop().toLowerCase();

    if (fileExtension !== '.pdf') {
      setErrorMessage('Only a single PDF file is allowed.');
      return;
    }
    if (file.size > MAX_FILE_SIZE) {
      setErrorMessage('File size too large (max 50MB).');
      return;
    }

    setSelectedFile(file);
  };

  const removeFile = () => {
    setSelectedFile(null);
    setErrorMessage('');
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleUpload = async () => {
    if (!selectedFile) {
      setErrorMessage('Select a PDF file to upload.');
      return;
    }

    setPhase('extracting');
    setErrorMessage('');

    try {
      const sanitizedAidYear = (aidYear || '').trim();
      if (!/^\d{4}$/.test(sanitizedAidYear)) {
        throw new Error('Aid year must be a 4-digit year.');
      }
      if (!['F', 'S'].includes(aidTerm)) {
        throw new Error('Aid term must be F or S.');
      }

      const result = await apiClient.uploadOutsideScholarshipsPdf(selectedFile, {
        aidYear: sanitizedAidYear,
        aidTerm,
      });

      if (!result || !Array.isArray(result.checks)) {
        throw new Error('Unexpected response from extraction.');
      }

      setPreview({
        ...result,
        filename: selectedFile.name,
      });
      setPhase('review');
    } catch (error) {
      setErrorMessage(error.message || 'Upload failed. Please try again.');
      setPhase('error');
    }
  };

  if (reviewing && preview) {
    return (
      <OutsideScholarshipsReview
        preview={preview}
        returnFocusRef={triggerRef}
        onClose={() => {
          resetState();
          onClose();
        }}
      />
    );
  }

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) handleClose();
      }}
    >
      <DialogContent
        className="sm:max-w-xl"
        onInteractOutside={(event) => {
          if (extracting) event.preventDefault();
        }}
        onEscapeKeyDown={(event) => {
          if (extracting) event.preventDefault();
        }}
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileCheck className="h-5 w-5" />
            Upload Outside Scholarship Checks
          </DialogTitle>
          <DialogDescription>
            Upload one PDF of scanned checks. Put each check&apos;s front first, followed by
            its back if you have it. Checks without a back are fine.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {!selectedFile && (
            <div className="border-2 border-dashed border-muted-foreground/25 rounded-lg p-6 text-center">
              <p className="text-sm text-muted-foreground mb-3">
                Select a single PDF file to upload.
              </p>
              <Button
                ref={triggerRef}
                variant="outline"
                onClick={() => fileInputRef.current?.click()}
                disabled={extracting}
              >
                Choose PDF File
              </Button>
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                accept=".pdf"
                onChange={(e) => handleFileSelect(e.target.files)}
              />
            </div>
          )}

          {selectedFile && (
            <div className="border rounded-lg p-3">
              <div className="flex items-center gap-3">
                <FileText className="h-5 w-5 text-blue-500 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{selectedFile.name}</p>
                  <p className="text-xs text-muted-foreground">{formatFileSize(selectedFile.size)}</p>
                </div>
                {!extracting && (
                  <Button variant="ghost" size="sm" onClick={removeFile}>
                    <X className="h-4 w-4" />
                  </Button>
                )}
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-sm font-medium">Aid year</label>
              <input
                type="text"
                inputMode="numeric"
                maxLength={4}
                value={aidYear}
                onChange={(e) => setAidYear(e.target.value)}
                disabled={extracting}
                className="w-full rounded-md border px-3 py-2 text-sm focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-offset-2 focus-visible:outline-navy"
                placeholder="YYYY"
              />
            </div>
            <div className="space-y-1">
              <label className="text-sm font-medium">Aid term</label>
              <select
                value={aidTerm}
                onChange={(e) => setAidTerm(e.target.value)}
                disabled={extracting}
                className="w-full rounded-md border px-3 py-2 text-sm bg-background focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-offset-2 focus-visible:outline-navy"
              >
                <option value="F">F</option>
                <option value="S">S</option>
              </select>
            </div>
          </div>

          {errorMessage && (
            <Alert className="border-red-200 bg-red-50">
              <AlertDescription className="text-red-800">{errorMessage}</AlertDescription>
            </Alert>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={handleClose} disabled={extracting}>
            Cancel
          </Button>
          <Button onClick={handleUpload} disabled={extracting || !selectedFile}>
            {extracting ? 'Extracting checks…' : 'Upload Check PDF'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
