"use client";

import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";


export default function AccessRestrictedPage() {
    const router = useRouter();
    return (
        <div className="flex flex-col items-center justify-center h-screen">
            <h1>Access Restricted</h1>
            <p>You are not authorized to access this page</p>
            <Button onClick={() => router.push('/')}>Return to Home</Button>
        </div>
    );
}