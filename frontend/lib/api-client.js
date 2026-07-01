// api-client.js - Updated for MSAL authentication

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  'https://charlotte-backend.azurewebsites.net';

const API_ENDPOINTS = {
  userDepartment: `${API_BASE_URL}/auth/user-department`,
  chat: `${API_BASE_URL}/api/chat`,
  query: `${API_BASE_URL}/api/query`,
  uploadEdi: `${API_BASE_URL}/api/upload-edi-report`,
  uploadAlignRx: `${API_BASE_URL}/api/alignrx/upload-report`,
  ediAnalyze: `${API_BASE_URL}/api/edi/analyze`,
  ediExport: `${API_BASE_URL}/api/edi/export`,
  ediReports: `${API_BASE_URL}/api/edi/reports`,
  alignrxAnalyze: `${API_BASE_URL}/api/alignrx/analyze`,
  alignrxExport: `${API_BASE_URL}/api/alignrx/export`,
  ediDashboardData: `${API_BASE_URL}/api/edi/dashboard_data`,
  uploadBankingFiles: `${API_BASE_URL}/api/banking/upload-files`,
  outsideScholarships: `${API_BASE_URL}/api/banking/outside-scholarships`,
};

// Create API client that requires auth headers to be passed in
export class APIClient {
  constructor(getAuthHeaders) {
    this.getAuthHeaders = getAuthHeaders;
  }

  async uploadBankingFiles(files) {
    try {
      const authHeaders = await this.getAuthHeaders();
      const formData = new FormData();
      files.forEach((file) => {
        formData.append("files", file);
      });

      const response = await fetch(API_ENDPOINTS.uploadBankingFiles, {
        method: "POST",
        headers: {
          ...authHeaders,
        },
        body: formData,
      });

      if (response.status === 401) {
        throw new Error('Authentication required');
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `API error: ${response.status}`);
      }

      const blob = await response.blob();
      const contentDisposition = response.headers.get("content-disposition") || "";
      const filenameMatch = contentDisposition.match(/filename="?([^"]+)"?/i);
      const filename = filenameMatch ? filenameMatch[1] : "banking_files.xlsx";
      return { blob, filename };
    } catch (error) {
      console.error("Upload banking files failed:", error);
      throw error;
    }
  }
  async uploadOutsideScholarshipsPdf(file, options = {}) {
    try {
      const { aidYear, aidTerm } = options;
      const authHeaders = await this.getAuthHeaders();
      const formData = new FormData();
      formData.append("files", file);
      if (aidYear) {
        formData.append("aid_year", String(aidYear));
      }
      if (aidTerm) {
        formData.append("aid_term", String(aidTerm));
      }

      const response = await fetch(API_ENDPOINTS.outsideScholarships, {
        method: "POST",
        headers: {
          ...authHeaders,
        },
        body: formData,
      });

      if (response.status === 401) {
        throw new Error('Authentication required');
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `API error: ${response.status}`);
      }

      const contentType = response.headers.get("content-type") || "";
      if (contentType.includes("application/json")) {
        return await response.json();
      }

      if (
        contentType.includes("spreadsheet") ||
        contentType.includes("excel") ||
        contentType.includes("octet-stream")
      ) {
        const blob = await response.blob();
        const contentDisposition = response.headers.get("content-disposition") || "";
        const filenameMatch = contentDisposition.match(/filename="?([^"]+)"?/i);
        const filename = filenameMatch ? filenameMatch[1] : "outside_scholarships.xlsx";
        return { blob, filename };
      }

      return await response.json().catch(() => ({}));
    } catch (error) {
      console.error("Upload outside scholarships PDF failed:", error);
      throw error;
    }
  }

  async getUserDepartment() {
    try {
      const authHeaders = await this.getAuthHeaders();
      const response = await fetch(API_ENDPOINTS.userDepartment, {
        headers: {
          ...authHeaders,
        },
      });
      if (response.status === 401) {
        throw new Error('Authentication required');
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `API error: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error("Get user department failed:", error);
      throw error;
    }
  }

  async sendChatQuery({ query, conversation_id, messages, mode }) {
    try {
      const authHeaders = await this.getAuthHeaders();
      
      const response = await fetch(API_ENDPOINTS.chat, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders,
        },
        body: JSON.stringify({
          query,
          conversation_id,
          messages,
          mode,
        }),
      });

      if (response.status === 401) {
        throw new Error('Authentication required');
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `API error: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error("API call failed:", error);
      throw error;
    }
  }

  async sendQuery({ query }) {
    try {
      const authHeaders = await this.getAuthHeaders();
      
      const response = await fetch(API_ENDPOINTS.query, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders,
        },
        body: JSON.stringify({ query }),
      });

      if (response.status === 401) {
        throw new Error('Authentication required');
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `API error: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error("Query API call failed:", error);
      throw error;
    }
  }

  async uploadEDIReport(file, onProgress) {
    try {
      const formData = new FormData();
      formData.append('file', file);

      const authHeaders = await this.getAuthHeaders();
      
      if (!authHeaders.Authorization) {
        throw new Error('Authentication required');
      }

      return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();

        // Track upload progress
        xhr.upload.onprogress = (event) => {
          if (event.lengthComputable && onProgress) {
            const percentComplete = (event.loaded / event.total) * 100;
            onProgress(Math.round(percentComplete));
          }
        };

        // Handle completion
        xhr.onload = () => {
          if (xhr.status === 200) {
            try {
              const response = JSON.parse(xhr.responseText);
              resolve(response);
            } catch (e) {
              reject(new Error('Invalid response format'));
            }
          } else if (xhr.status === 409) {
            // Handle duplicate file conflict
            try {
              const errorResponse = JSON.parse(xhr.responseText);
              reject(new Error(`Duplicate: ${errorResponse.detail || 'File already exists'}`));
            } catch (e) {
              reject(new Error('Duplicate: File already exists'));
            }
          } else {
            try {
              const errorResponse = JSON.parse(xhr.responseText);
              reject(new Error(errorResponse.detail || `Upload failed with status ${xhr.status}`));
            } catch (e) {
              reject(new Error(`Upload failed with status ${xhr.status}`));
            }
          }
        };

        // Handle errors
        xhr.onerror = () => {
          reject(new Error('Network error occurred during upload'));
        };

        // Start upload
        xhr.open('POST', API_ENDPOINTS.uploadEdi);
        xhr.setRequestHeader('Authorization', authHeaders.Authorization);
        xhr.send(formData);
      });

    } catch (error) {
      console.error("Upload error:", error);
      throw error;
    }
  }

  async uploadMultipleEDIReports(files, onProgress, onFileComplete) {
    const results = [];
    let totalFiles = files.length;
    let completedFiles = 0;

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      try {
        const result = await this.uploadEDIReport(file, (progress) => {
          // Calculate overall progress
          const overallProgress = ((completedFiles * 100) + progress) / totalFiles;
          onProgress(Math.round(overallProgress), i, file.name);
        });

        results.push({ file: file.name, success: true, result });
        completedFiles++;

        if (onFileComplete) {
          onFileComplete(file.name, true, result, null);
        }
      } catch (error) {
        results.push({ file: file.name, success: false, error: error.message });
        completedFiles++;

        if (onFileComplete) {
          onFileComplete(file.name, false, null, error.message);
        }
      }
    }

    return results;
  }

  async uploadAlignRxReport(file, onProgress) {
    try {
      const formData = new FormData();
      formData.append('file', file);

      const authHeaders = await this.getAuthHeaders();

      if (!authHeaders.Authorization) {
        throw new Error('Authentication required');
      }

      return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();

        xhr.upload.onprogress = (event) => {
          if (event.lengthComputable && onProgress) {
            const percentComplete = (event.loaded / event.total) * 100;
            onProgress(Math.round(percentComplete));
          }
        };

        xhr.onload = () => {
          if (xhr.status === 200) {
            try {
              const response = JSON.parse(xhr.responseText);
              resolve(response);
            } catch (e) {
              reject(new Error('Invalid response format'));
            }
          } else if (xhr.status === 409) {
            try {
              const errorResponse = JSON.parse(xhr.responseText);
              reject(new Error(`Duplicate: ${errorResponse.detail || 'File already exists'}`));
            } catch (e) {
              reject(new Error('Duplicate: File already exists'));
            }
          } else {
            try {
              const errorResponse = JSON.parse(xhr.responseText);
              reject(new Error(errorResponse.detail || `Upload failed with status ${xhr.status}`));
            } catch (e) {
              reject(new Error(`Upload failed with status ${xhr.status}`));
            }
          }
        };

        xhr.onerror = () => {
          reject(new Error('Network error occurred during upload'));
        };

        xhr.open('POST', API_ENDPOINTS.uploadAlignRx);
        xhr.setRequestHeader('Authorization', authHeaders.Authorization);
        xhr.send(formData);
      });
    } catch (error) {
      console.error('AlignRx upload error:', error);
      throw error;
    }
  }

  async analyzeEdiRange({ start, end, mode }) {
    try {
      const authHeaders = await this.getAuthHeaders();
      const response = await fetch(API_ENDPOINTS.ediAnalyze, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders,
        },
        body: JSON.stringify({ start, end, mode }),
      });

      if (response.status === 401) {
        throw new Error('Authentication required');
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `API error: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error("Analyze EDI range failed:", error);
      throw error;
    }
  }


  async downloadEdiExcel({ start, end, mode }) {
    try {
      const authHeaders = await this.getAuthHeaders();
      const response = await fetch(API_ENDPOINTS.ediExport, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders,
        },
        body: JSON.stringify({ start, end, mode }),
      });

      if (response.status === 401) {
        throw new Error('Authentication required');
      }

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(errorText || `API error: ${response.status}`);
      }

      const blob = await response.blob();
      return blob;
    } catch (error) {
      console.error("Download EDI Excel failed:", error);
      throw error;
    }
  }

  async analyzeAlignRxRange({ start, end }) {
    try {
      const authHeaders = await this.getAuthHeaders();
      const response = await fetch(API_ENDPOINTS.alignrxAnalyze, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders,
        },
        body: JSON.stringify({ start, end }),
      });

      if (response.status === 401) {
        throw new Error('Authentication required');
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `API error: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error("Analyze AlignRx range failed:", error);
      throw error;
    }
  }

  async downloadAlignRxExcel({ start, end }) {
    try {
      const authHeaders = await this.getAuthHeaders();
      const response = await fetch(API_ENDPOINTS.alignrxExport, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders,
        },
        body: JSON.stringify({ start, end }),
      });

      if (response.status === 401) {
        throw new Error('Authentication required');
      }

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(errorText || `API error: ${response.status}`);
      }

      const blob = await response.blob();
      return blob;
    } catch (error) {
      console.error("Download AlignRx Excel failed:", error);
      throw error;
    }
  }

  async getEdiReports({ page = 1, pageSize = 20 } = {}) {
    try {
      const authHeaders = await this.getAuthHeaders();
      const url = new URL(API_ENDPOINTS.ediReports);
      url.searchParams.set('page', page);
      url.searchParams.set('page_size', pageSize);
      
      const response = await fetch(url.toString(), {
        headers: {
          ...authHeaders,
        },
      });

      if (response.status === 401) {
        throw new Error('Authentication required');
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `API error: ${response.status}`);
      }

      return await response.json();
    } catch (error) { 
      console.error("Get EDI reports failed:", error);
      throw error;
    }
  }

  async getEdiReport(filename) {
    try {
      const authHeaders = await this.getAuthHeaders();
      const response = await fetch(`${API_ENDPOINTS.ediReports}/${encodeURIComponent(filename)}`, {
        headers: {
          ...authHeaders,
        },
      });

      if (response.status === 401) {
        throw new Error('Authentication required');
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `API error: ${response.status}`);
      }

      return response; // Return the response object so we can get the blob
    } catch (error) { 
      console.error("Get EDI report failed:", error);
      throw error;
    }
  }
  async getEdiDashboardData() {
    try {
      const authHeaders = await this.getAuthHeaders();
      const response = await fetch(API_ENDPOINTS.ediDashboardData, {
        headers: {
          ...authHeaders,
        },
      }); 
      if (response.status === 401) {
        throw new Error('Authentication required');
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `API error: ${response.status}`);
      }
      return await response.json();
    }
    catch (error) {
      console.error("Get EDI dashboard data failed:", error);
      throw error;
    }
  }
}

// All components now use APIClient class - no deprecated functions needed
