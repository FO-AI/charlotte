'use client';

import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import Navigation from '@/components/accounting/navigation';

const AdminLanding = () => {    
    const router = useRouter();
    
    const departments = [
        {
            title: "Accounting",
            description: "Access financial reports, EDI transactions, and AlignRx analysis tools",
            icon: (
                <svg className="w-10 h-10 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                </svg>
            ),
            route: "/dashboard/accounting",
            gradient: "from-[#4B9CD3] to-[#2B6FA6]"
        },
        {
            title: "Banking",
            description: "Manage banking operations, transactions, and financial data",
            icon: (
                <svg className="w-10 h-10 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
                </svg>
            ),
            route: "/dashboard/banking",
            gradient: "from-[#2B6FA6] to-[#1A5276]"
        }
    ];

    return (
        <div className="min-h-screen bg-background">
    
            {/* Hero Section */}
            <section className="hero-gradient pt-14 pb-10 md:pt-24 md:pb-18 relative overflow-hidden">
                <div className="container mx-auto px-4 relative z-10">
                    <div className="max-w-4xl mx-auto">
                        <div className="text-center space-y-8">
                            {/* Icon */}
                            <div className="fade-in-up inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-[#4B9CD3] to-[#2B6FA6] mb-5 shadow-lg">
                                <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                                </svg>
                            </div>
                            
                            {/* Main Headline */}
                            <div className="space-y-6">
                                <h1 className="fade-in-up text-4xl md:text-5xl lg:text-6xl font-bold text-foreground tracking-tight leading-tight">
                                    Admin <span className="gradient-text">Dashboard</span>
                                </h1>
                                <p className="fade-in-up-delay-1 text-lg md:text-xl text-muted-foreground max-w-3xl mx-auto leading-relaxed font-light">
                                    Select a department to access specialized tools and reports
                                </p>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            {/* Department Cards Section */}
            <section className="section-spacing bg-gradient-to-b from-background via-muted/20 to-background">
                <div className="container mx-auto px-4">
                    <div className="max-w-5xl mx-auto">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                            {departments.map((dept, index) => (
                                <Card 
                                    key={index}
                                    className="fade-in-up-delay-2 border-2 border-primary/20 bg-card/60 backdrop-blur-sm shadow-xl hover:shadow-2xl hover:border-primary/40 transition-all duration-300 hover-lift cursor-pointer group"
                                    onClick={() => router.push(dept.route)}
                                >
                                    <CardContent className="p-8 md:p-10">
                                        <div className="space-y-6">
                                            {/* Icon */}
                                            <div className={`inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br ${dept.gradient} shadow-lg transition-all duration-300 group-hover:scale-110 group-hover:shadow-xl`}>
                                                {dept.icon}
                                            </div>
                                            
                                            {/* Content */}
                                            <div className="space-y-3">
                                                <h2 className="text-3xl md:text-4xl font-bold text-foreground tracking-tight">
                                                    {dept.title}
                                                </h2>
                                                <p className="text-lg text-muted-foreground leading-relaxed">
                                                    {dept.description}
                                                </p>
                                            </div>
                                            
                                            {/* Arrow Icon */}
                                            <div className="flex items-center text-primary group-hover:translate-x-2 transition-transform duration-300">
                                                <span className="text-sm font-semibold mr-2">Access Dashboard</span>
                                                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
                                                </svg>
                                            </div>
                                        </div>
                                    </CardContent>
                                </Card>
                            ))}
                        </div>
                    </div>
                </div>
            </section>

            {/* Footer */}
            <footer className="py-16 md:py-20 bg-gradient-to-b from-background to-secondary/30 border-t border-primary/10">
                <div className="container mx-auto px-4">
                    <div className="max-w-6xl mx-auto">
                        <div className="flex flex-col md:flex-row justify-between items-center space-y-6 md:space-y-0">
                            <div className="flex items-center space-x-3 group cursor-pointer">
                                <div className="w-12 h-12 bg-gradient-to-br from-[#4B9CD3] to-[#2B6FA6] rounded-xl flex items-center justify-center shadow-lg transition-all duration-300 group-hover:scale-110 group-hover:shadow-xl">
                                    <span className="text-white font-bold text-xl">C</span>
                                </div>
                                <span className="text-2xl font-bold text-foreground">Charlotte</span>
                            </div>
                            <div className="text-center md:text-right">
                                <p className="text-base text-muted-foreground font-medium">
                                    © 2024 Charlotte. Built for <span className="text-primary font-semibold">UNC employees</span>.
                                </p>
                            </div>
                        </div>
                    </div>
                </div>
            </footer>
        </div>
    );
};

export default AdminLanding;