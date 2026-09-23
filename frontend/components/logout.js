/**
 * User menu for the site header.
 * Shows session timer and sign-out for authenticated users.
 */

'use client';

import { useCallback } from "react";
import { LogOut, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth/auth-context-msal";
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

  const handleSessionExpired = useCallback(() => {
    logout();
  }, [logout]);

  if (!isAuthenticated() || !user) {
    return null;
  }

  return (
    <div className="flex items-center gap-3">
      <SessionTimer onSessionExpired={handleSessionExpired} />
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            className="min-h-10 min-w-10 gap-2 text-navy hover:bg-cloud"
            aria-label={`Account menu for ${user.given_name || user.name}`}
          >
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-navy text-white">
              <User className="h-4 w-4" aria-hidden="true" />
            </span>
            <span className="hidden font-medium sm:inline">
              {user.given_name || user.name}
            </span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-64">
          <DropdownMenuLabel>
            <div className="space-y-1">
              <p className="font-semibold text-foreground">{user.name}</p>
              <p className="text-sm text-muted-foreground">{user.email}</p>
              {user.department && (
                <p className="text-sm text-muted-foreground">{user.department}</p>
              )}
            </div>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={logout} className="text-destructive cursor-pointer">
            <LogOut className="h-4 w-4 mr-2" aria-hidden="true" />
            Sign out
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
