'use client';

import { useState, useRef } from 'react';
import { X, FileCheck, FileText } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { APIClient } from '@/lib/api-client';
import { useAuth } from '@/lib/auth/auth-context-msal';

const MAX_FILE_SIZE = 50 * 1024 * 1024;

function formatFileSize(bytes) {
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(0)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function OutsideScholarshipsUploadModal({ isOpen, onClose }) {
  const { getAuthHeaders } = useAuth();
  const apiClient = new APIClient(getAuthHeaders);
  const defaultAidYear = String(new Date().getFullYear());
  const [selectedFile, setSelectedFile] = useState(null);
  const [aidYear, setAidYear] = useState(defaultAidYear);
  const [aidTerm, setAidTerm] = useState('F');
  const [uploading, setUploading] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [successMessage, setSuccessMessage] = useState('');
  const fileInputRef = useRef(null);

  const resetState = () => {
    setSelectedFile(null);
    setAidYear(defaultAidYear);
    setAidTerm('F');
    setUploading(false);
    setErrorMessage('');
    setSuccessMessage('');
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleClose = () => {
    if (uploading) return;
    resetState();
    onClose();
  };

  const handleFileSelect = (files) => {
    if (!files || files.length === 0) return;
    setErrorMessage('');
    setSuccessMessage('');

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
    setSuccessMessage('');
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleUpload = async () => {
    if (!selectedFile) {
      setErrorMessage('Select a PDF file to upload.');
      return;
    }

    setUploading(true);
    setErrorMessage('');
    setSuccessMessage('');

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

      if (result && result.blob) {
        const url = window.URL.createObjectURL(result.blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = result.filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.URL.revokeObjectURL(url);
        setSuccessMessage('Upload complete. Your Excel file has been downloaded.');
      } else if (result && Array.isArray(result.checks)) {
        setSuccessMessage(`Upload complete. Processed ${result.checks.length} check page(s).`);
      } else {
        setSuccessMessage('Upload complete.');
      }
    } catch (error) {
      setErrorMessage(error.message || 'Upload failed. Please try again.');
    } finally {
      setUploading(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileCheck className="h-5 w-5" />
            Upload Outside Scholarship Checks
          </DialogTitle>
          <DialogDescription>
            Upload one PDF containing scanned check fronts and backs. Pages should be
            ordered front, back, front, back. Each two-page pair represents one check.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {!selectedFile && (
            <div className="border-2 border-dashed border-muted-foreground/25 rounded-lg p-6 text-center">
              <p className="text-sm text-muted-foreground mb-3">
                Select a single PDF file to upload.
              </p>
              <Button
                variant="outline"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading}
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
                {!uploading && (
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
                disabled={uploading}
                className="w-full rounded-md border px-3 py-2 text-sm"
                placeholder="YYYY"
              />
            </div>
            <div className="space-y-1">
              <label className="text-sm font-medium">Aid term</label>
              <select
                value={aidTerm}
                onChange={(e) => setAidTerm(e.target.value)}
                disabled={uploading}
                className="w-full rounded-md border px-3 py-2 text-sm bg-background"
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

          {successMessage && (
            <Alert className="border-green-200 bg-green-50">
              <AlertDescription className="text-green-800">{successMessage}</AlertDescription>
            </Alert>
          )}
        </div>

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={handleClose} disabled={uploading}>
            Close
          </Button>
          <Button onClick={handleUpload} disabled={uploading || !selectedFile}>
            {uploading ? 'Uploading...' : 'Upload Check PDF'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
