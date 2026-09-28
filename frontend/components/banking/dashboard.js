'use client';

import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import BankingUploadModal from '@/components/banking/upload-modal';
import OutsideScholarshipsUploadModal from '@/components/banking/outside-scholarships-upload-modal';
import {
  FileText,
  Database,
  Upload,
  FileCheck
} from 'lucide-react';

export default function BankingDashboard() {
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [showOutsideScholarshipsModal, setShowOutsideScholarshipsModal] = useState(false);

  const quickActions = [
    {
      title: 'Upload Banking Files',
      description: 'Upload banking files for analysis',
      icon: Upload,
      onClick: () => setShowUploadModal(true),
      gradient: 'from-[#2B6FA6] to-[#4B9CD3]',
      iconBg: 'bg-[#2B6FA6]/10'
    },
    {
      title: 'Outside Scholarships',
      description: 'Upload scanned front/back check PDF',
      icon: FileCheck,
      onClick: () => setShowOutsideScholarshipsModal(true),
      gradient: 'from-[#4B9CD3] to-[#2B6FA6]',
      iconBg: 'bg-[#4B9CD3]/10'
    }
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-background via-[rgba(75,156,211,0.03)] to-background relative overflow-hidden">
      {/* Background decorative elements */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-0 right-0 w-96 h-96 bg-[#4B9CD3]/5 rounded-full blur-3xl"></div>
        <div className="absolute bottom-0 left-0 w-96 h-96 bg-[#2B6FA6]/5 rounded-full blur-3xl"></div>
      </div>

      <div className="container mx-auto px-4 md:px-6 py-8 md:py-12 max-w-7xl relative z-10">
        <BankingUploadModal
          isOpen={showUploadModal}
          onClose={() => setShowUploadModal(false)}
        />
        <OutsideScholarshipsUploadModal
          isOpen={showOutsideScholarshipsModal}
          onClose={() => setShowOutsideScholarshipsModal(false)}
        />
        {/* Header Section */}
        <div className="mb-12 fade-in-up">
          <div className="flex items-center gap-4 mb-4">
            <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-[#4B9CD3] to-[#2B6FA6] flex items-center justify-center shadow-lg">
              <Database className="h-7 w-7 text-white" />
            </div>
            <div>
              <h1 className="text-4xl md:text-5xl lg:text-6xl font-bold text-foreground tracking-tight">
                Banking Dashboard
              </h1>
            </div>
          </div>
          <p className="text-lg md:text-xl text-muted-foreground md:ml-[4.5rem]">
            Welcome to <span className="font-semibold text-[#4B9CD3]">Charlotte</span> - Your AI-powered banking data management platform
          </p>
        </div>

        {/* Quick Actions Section */}
        <div className="mb-12">
          <div className="mb-8 fade-in-up-delay-2">
            <h2 className="text-3xl md:text-4xl font-bold text-foreground mb-3 tracking-tight">
              Quick <span className="bg-gradient-to-r from-[#4B9CD3] to-[#2B6FA6] bg-clip-text text-transparent">Actions</span>
            </h2>
            <p className="text-muted-foreground">Access key features and tools instantly</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {quickActions.map((action, index) => {
              const delayClass = index < 3 ? `fade-in-up-delay-${index + 1}` : `fade-in-up-delay-${(index % 3) + 1}`;
              return (
                <Card 
                  key={index} 
                  className={`${delayClass} group cursor-pointer border-2 border-primary/10 bg-card/80 backdrop-blur-sm shadow-lg hover:shadow-2xl hover:border-primary/30 transition-all duration-300 transform hover:-translate-y-2 hover:scale-[1.02] relative overflow-hidden`}
                  onClick={action.onClick}
                >
                  {/* Gradient background on hover */}
                  <div className={`absolute inset-0 bg-gradient-to-br ${action.gradient} opacity-0 group-hover:opacity-5 transition-opacity duration-300`}></div>
                  
                  <CardHeader className="text-center pb-4 pt-8 relative z-10">
                    <div className={`mx-auto w-20 h-20 rounded-2xl ${action.iconBg} flex items-center justify-center mb-4 group-hover:scale-110 group-hover:rotate-3 transition-all duration-300`}>
                      <action.icon className={`h-10 w-10 text-[#4B9CD3] group-hover:text-[#2B6FA6] transition-colors duration-300`} />
                    </div>
                    <CardTitle className="text-xl font-bold text-foreground group-hover:text-[#4B9CD3] transition-colors duration-300">
                      {action.title}
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="text-center pt-0 pb-8 relative z-10">
                    <CardDescription className="text-muted-foreground text-sm leading-relaxed">
                      {action.description}
                    </CardDescription>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </div>

        {/* Placeholder for future sections */}
        <div className="mb-8">
          <div className="mb-8 fade-in-up-delay-3">
            <h2 className="text-3xl md:text-4xl font-bold text-foreground mb-3 tracking-tight">
              Recent <span className="bg-gradient-to-r from-[#4B9CD3] to-[#2B6FA6] bg-clip-text text-transparent">Activity</span>
            </h2>
            <p className="text-muted-foreground">Your most recently processed reports and transactions</p>
          </div>
          <Card className="border-2 border-primary/10 bg-card/80 backdrop-blur-sm shadow-xl fade-in-up-delay-4">
            <CardHeader className="pb-6">
              <CardTitle className="flex items-center gap-3 text-2xl font-bold text-foreground">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-[#4B9CD3]/20 to-[#2B6FA6]/20 flex items-center justify-center">
                  <FileText className="h-5 w-5 text-[#4B9CD3]" />
                </div>
                Latest Banking Reports
              </CardTitle>
              <CardDescription className="text-base text-muted-foreground mt-2">
                Your most recently processed banking reports
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="text-center py-12 text-muted-foreground">
                <p>No recent banking reports found</p>
                <p className="text-sm mt-2">This section will be populated as features are implemented</p>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
