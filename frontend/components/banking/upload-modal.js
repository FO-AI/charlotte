'use client';

import { useState, useRef } from 'react';
import { X, Upload, FileText } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { APIClient } from '@/lib/api-client';
import { useAuth } from '@/lib/auth/auth-context-msal';


export default function BankingUploadModal({ isOpen, onClose }) {
    const { getAuthHeaders } = useAuth();
    const apiClient = new APIClient(getAuthHeaders);
    const [selectedFiles, setSelectedFiles] = useState([]);
    const [uploading, setUploading] = useState(false);
    const [errorMessage, setErrorMessage] = useState('');
    const [successMessage, setSuccessMessage] = useState('');
    const fileInputRef = useRef(null);
  
    const allowedTypes = ['.pdf'];
    const maxFileSize = 50 * 1024 * 1024;
    const maxFiles = 15;
  
    const resetState = () => {
      setSelectedFiles([]);
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
  
      const currentCount = selectedFiles.length;
      const incoming = Array.from(files);
      const remainingSlots = maxFiles - currentCount;
  
      if (remainingSlots <= 0) {
        setErrorMessage(`You can upload up to ${maxFiles} files.`);
        return;
      }
  
      const validFiles = [];
      const errors = [];
  
      incoming.slice(0, remainingSlots).forEach((file) => {
        const fileExtension = '.' + file.name.split('.').pop().toLowerCase();
        if (!allowedTypes.includes(fileExtension)) {
          errors.push(`${file.name}: Only PDF files are allowed`);
          return;
        }
        if (file.size > maxFileSize) {
          errors.push(`${file.name}: File size too large (max 50MB)`);
          return;
        }
        if (selectedFiles.some((existing) => existing.name === file.name)) {
          errors.push(`${file.name}: File already selected`);
          return;
        }
        validFiles.push(file);
      });
  
      if (incoming.length > remainingSlots) {
        errors.push(`Only ${remainingSlots} more file(s) allowed (max ${maxFiles}).`);
      }
  
      if (errors.length > 0) {
        setErrorMessage(errors.join(', '));
      }
  
      if (validFiles.length > 0) {
        setSelectedFiles((prev) => [...prev, ...validFiles]);
      }
    };
  
    const removeFile = (index) => {
      setSelectedFiles((prev) => prev.filter((_, i) => i !== index));
      setErrorMessage('');
      setSuccessMessage('');
    };
  
    const handleUpload = async () => {
      if (selectedFiles.length === 0) {
        setErrorMessage('Select at least one file to upload.');
        return;
      }
  
      setUploading(true);
      setErrorMessage('');
      setSuccessMessage('');
  
      try {
        const { blob, filename } = await apiClient.uploadBankingFiles(selectedFiles);
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.URL.revokeObjectURL(url);
        setSuccessMessage('Upload complete. Your consolidated Excel file has been downloaded.');
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
              <Upload className="h-5 w-5" />
              Upload Banking Files
            </DialogTitle>
            <DialogDescription>
              Upload up to {maxFiles} PDF files. A consolidated Excel file will download when processing is complete.
            </DialogDescription>
          </DialogHeader>
  
          <div className="space-y-4">
            <div className="border-2 border-dashed border-muted-foreground/25 rounded-lg p-6 text-center">
              <p className="text-sm text-muted-foreground mb-3">
                Select PDF files to upload (max {maxFiles}).
              </p>
              <Button
                variant="outline"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading}
              >
                Choose Files
              </Button>
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                accept={allowedTypes.join(',')}
                multiple
                onChange={(e) => handleFileSelect(e.target.files)}
              />
            </div>
  
            {selectedFiles.length > 0 && (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <h4 className="text-sm font-medium">Selected Files ({selectedFiles.length})</h4>
                  {!uploading && (
                    <Button variant="ghost" size="sm" onClick={() => setSelectedFiles([])}>
                      Clear All
                    </Button>
                  )}
                </div>
                <div className="max-h-40 overflow-y-auto space-y-2">
                  {selectedFiles.map((file, index) => (
                    <div key={`${file.name}-${index}`} className="border rounded-lg p-3">
                      <div className="flex items-center gap-3">
                        <FileText className="h-5 w-5 text-blue-500 flex-shrink-0" />
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium truncate">{file.name}</p>
                        </div>
                        {!uploading && (
                          <Button variant="ghost" size="sm" onClick={() => removeFile(index)}>
                            <X className="h-4 w-4" />
                          </Button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
  
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
            <Button onClick={handleUpload} disabled={uploading || selectedFiles.length === 0}>
              {uploading ? 'Uploading...' : 'Upload Files'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    );
  }