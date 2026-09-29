'use client';

import OutsideScholarshipsUploadModal from '@/components/banking/outside-scholarships-upload-modal';

/**
 * Playwright harness: upload modal without MSAL (see MsalProviderWrapper E2E path).
 * Only available when NEXT_PUBLIC_ENABLE_E2E_HARNESS=1 under non-production (next dev).
 */
const E2E_HARNESS =
  process.env.NEXT_PUBLIC_ENABLE_E2E_HARNESS === '1' && process.env.NODE_ENV !== 'production';

export default function OutsideScholarshipsE2EPage() {
  if (!E2E_HARNESS) {
    return (
      <main className="min-h-screen p-6">
        <p>E2E harness disabled.</p>
      </main>
    );
  }

  return (
    <main className="min-h-screen p-6">
      <h1 className="text-xl font-semibold mb-4">Outside scholarships e2e harness</h1>
      <OutsideScholarshipsUploadModal isOpen onClose={() => {}} />
    </main>
  );
}
