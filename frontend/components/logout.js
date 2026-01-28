/**
 * Header component for the application
 * Contains navigation elements, user profile dropdown, and action buttons
 * Handles authentication state and provides access to key features like:
 *  - File upload
 *  - Data analysis
 *  - Search index updates
 *  - User profile/logout
 * Used across all pages to maintain consistent navigation and functionality
 */

'use client';

import { useRouter } from "next/navigation";
import { useState, useCallback } from "react";
import UploadModal from "@/components/accounting/upload-modal";
import { Database, LogOut, User, Upload, RefreshCw , ChartArea, FileSpreadsheet} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth/auth-context-msal";
import { FileText } from "lucide-react";
import AlignRxUploadModal from "@/components/accounting/align-rx/align-rx-upload-modal";
import SessionTimer from "@/components/session-timer";





import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";


export default function Logout() {
  const { user, logout, isAuthenticated } = useAuth();
  
  // Memoize to prevent recreation on every render
  const handleSessionExpired = useCallback(() => {
    logout();
  }, [logout]);

  return (
    <div className="fixed top-4 right-4 z-50 fade-in-up">
      <div className="bg-background/90 backdrop-blur-md border-2 border-primary/20 rounded-2xl shadow-2xl p-2">
      <div className="flex items-center gap-3">
        {isAuthenticated() && user && (
          <>
            <SessionTimer onSessionExpired={handleSessionExpired} />
            <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button 
                variant="ghost" 
                size="default" 
                className="flex items-center gap-2 px-4 py-2 hover:bg-[#4B9CD3]/10 transition-all duration-300 rounded-xl"
              >
                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[#4B9CD3] to-[#2B6FA6] flex items-center justify-center">
                  <User className="h-4 w-4 text-white" />
                </div>
                <span className="hidden sm:inline font-medium text-foreground">{user.given_name || user.name}</span>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-64 bg-card/95 backdrop-blur-md border-2 border-primary/20 shadow-2xl rounded-xl">
              <DropdownMenuLabel>
                <div className="space-y-1">
                  <p className="font-semibold text-foreground">{user.name}</p>
                  <p className="text-sm text-muted-foreground">{user.email}</p>
                  {user.department && (
                    <p className="text-xs text-muted-foreground">{user.department}</p>
                  )}
                </div>
              </DropdownMenuLabel>
              <DropdownMenuSeparator className="bg-primary/10" />
              <DropdownMenuItem 
                onClick={logout} 
                className="text-destructive cursor-pointer hover:bg-destructive/10 transition-colors duration-300 rounded-lg"
              >
                <LogOut className="h-4 w-4 mr-2" />
                Sign out
              </DropdownMenuItem>
            </DropdownMenuContent>
            </DropdownMenu>
          </>
        )}
      </div>
    </div>
    </div>
  );
}