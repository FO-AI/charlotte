'use client';

import { useRouter } from 'next/navigation';
import { Card, CardContent } from '@/components/ui/card';

const departments = [
  {
    title: 'Accounting',
    description: 'Financial reports, EDI transactions, and AlignRx analysis tools.',
    route: '/dashboard/accounting',
  },
  {
    title: 'Banking',
    description: 'Banking operations, transactions, and financial data.',
    route: '/dashboard/banking',
  },
];

const AdminLanding = () => {
  const router = useRouter();

  return (
    <section className="content-section">
      <div className="site-wrap">
        <h1 className="text-navy text-4xl font-bold mb-3">Admin dashboard</h1>
        <p className="mb-10 max-w-2xl">
          Select a department to open its tools and reports.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {departments.map((dept) => (
            <Card key={dept.title} className="border-fordham hover:border-navy">
              <CardContent className="p-8">
                <h2 className="text-navy text-2xl font-bold mb-3">{dept.title}</h2>
                <p className="mb-4">{dept.description}</p>
                <button
                  type="button"
                  className="font-bold text-link min-h-6"
                  onClick={() => router.push(dept.route)}
                >
                  Open {dept.title} dashboard
                </button>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </section>
  );
};

export default AdminLanding;
