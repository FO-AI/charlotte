'use client';

import { useRef, useState } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import BankingUploadModal from '@/components/banking/upload-modal';
import OutsideScholarshipsUploadModal from '@/components/banking/outside-scholarships-upload-modal';
import { FileText, Upload, FileCheck } from 'lucide-react';

export default function BankingDashboard() {
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [showOutsideScholarshipsModal, setShowOutsideScholarshipsModal] = useState(false);
  const outsideScholarshipsCardRef = useRef(null);

  const tools = [
    {
      title: 'Upload banking files',
      description: 'Add banking files for processing and review.',
      action: 'Upload files',
      icon: Upload,
      onClick: () => setShowUploadModal(true),
    },
    {
      title: 'Outside scholarships',
      description: 'Upload a scanned front-and-back check PDF.',
      action: 'Upload check PDF',
      icon: FileCheck,
      onClick: () => setShowOutsideScholarshipsModal(true),
      cardRef: outsideScholarshipsCardRef,
    },
  ];

  return (
    <section className="content-section">
      <div className="site-wrap">
        <BankingUploadModal
          isOpen={showUploadModal}
          onClose={() => setShowUploadModal(false)}
        />
        <OutsideScholarshipsUploadModal
          isOpen={showOutsideScholarshipsModal}
          onClose={() => setShowOutsideScholarshipsModal(false)}
          returnFocusRef={outsideScholarshipsCardRef}
        />

        <h1 className="text-navy text-5xl md:text-6xl font-bold mb-10 text-center">Banking dashboard</h1>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-10">
          {tools.map((tool) => (
            <Card
              key={tool.title}
              ref={tool.cardRef}
              tabIndex={tool.cardRef ? 0 : undefined}
              className={`border-fordham hover:border-navy ${
                tool.cardRef
                  ? 'focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-offset-2 focus-visible:outline-navy'
                  : ''
              }`}
            >
              <CardContent className="p-8">
                <div className="flex items-start gap-4 mb-4">
                  <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-md bg-cloud text-navy">
                    <tool.icon className="h-6 w-6" aria-hidden="true" />
                  </div>
                  <div>
                    <h2 className="text-navy text-2xl font-bold mb-2">{tool.title}</h2>
                    <p className="mb-4">{tool.description}</p>
                    <button
                      type="button"
                      className="font-bold text-link min-h-6"
                      onClick={tool.onClick}
                    >
                      {tool.action}
                    </button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        <Card className="border-fordham">
          <CardContent className="p-8">
            <h2 className="text-navy text-2xl font-bold mb-2">Recent activity</h2>
            <div className="flex flex-col items-start gap-2 py-6 text-[var(--color-old-well)]">
              <FileText className="h-6 w-6 text-navy" aria-hidden="true" />
              <p>No banking reports yet.</p>
              <p className="text-sm">Uploaded files and processed checks will show up here.</p>
            </div>
          </CardContent>
        </Card>
      </div>
    </section>
  );
}
