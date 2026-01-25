'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { Clock } from 'lucide-react';

const SESSION_DURATION_MS = 30 * 60 * 1000; // 30 minutes
const WARNING_THRESHOLD_MS = 5 * 60 * 1000; // 5 minutes
const CRITICAL_THRESHOLD_MS = 1 * 60 * 1000; // 1 minute
const STORAGE_KEY = 'session_login_timestamp';

/**
 * Isolated SessionTimer component - manages its own state
 * This component does NOT use any context state that updates frequently,
 * so only THIS component re-renders every second, not the entire app.
 */
export default function SessionTimer({ onSessionExpired }) {
  const [remainingTime, setRemainingTime] = useState(null);
  const [isExpired, setIsExpired] = useState(false);
  const intervalRef = useRef(null);

  const calculateRemainingTime = useCallback(() => {
    const loginTimestamp = localStorage.getItem(STORAGE_KEY);
    if (!loginTimestamp) return null;
    
    const elapsed = Date.now() - parseInt(loginTimestamp, 10);
    const remaining = SESSION_DURATION_MS - elapsed;
    return Math.max(0, remaining);
  }, []);

  useEffect(() => {
    // Initial calculation
    const initial = calculateRemainingTime();
    setRemainingTime(initial);

    if (initial === null) return;

    // If already expired on mount
    if (initial <= 0) {
      setIsExpired(true);
      onSessionExpired?.();
      return;
    }

    // Update every second
    intervalRef.current = setInterval(() => {
      const remaining = calculateRemainingTime();
      
      if (remaining === null) {
        clearInterval(intervalRef.current);
        setRemainingTime(null);
        return;
      }

      setRemainingTime(remaining);

      if (remaining <= 0 && !isExpired) {
        setIsExpired(true);
        clearInterval(intervalRef.current);
        onSessionExpired?.();
      }
    }, 1000);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [calculateRemainingTime, onSessionExpired, isExpired]);

  // Don't render if no session timestamp
  if (remainingTime === null) return null;

  const minutes = Math.floor(remainingTime / 60000);
  const seconds = Math.floor((remainingTime % 60000) / 1000);
  const formattedTime = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;

  // Color based on remaining time
  let colorClasses = 'text-muted-foreground bg-muted/50'; // Normal - gray
  if (remainingTime <= CRITICAL_THRESHOLD_MS) {
    colorClasses = 'text-red-600 bg-red-100 dark:text-red-400 dark:bg-red-950/50 animate-pulse';
  } else if (remainingTime <= WARNING_THRESHOLD_MS) {
    colorClasses = 'text-amber-600 bg-amber-100 dark:text-amber-400 dark:bg-amber-950/50';
  }

  return (
    <div 
      className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-mono font-medium transition-colors duration-300 ${colorClasses}`}
      title="Session time remaining"
    >
      <Clock className="h-3 w-3" />
      <span>{formattedTime}</span>
    </div>
  );
}

// Utility functions for session management (to be called from auth-context)
export const sessionUtils = {
  startSession: () => {
    localStorage.setItem(STORAGE_KEY, Date.now().toString());
  },
  
  endSession: () => {
    localStorage.removeItem(STORAGE_KEY);
  },
  
  hasActiveSession: () => {
    const timestamp = localStorage.getItem(STORAGE_KEY);
    if (!timestamp) return false;
    const elapsed = Date.now() - parseInt(timestamp, 10);
    return elapsed < SESSION_DURATION_MS;
  },

  getStorageKey: () => STORAGE_KEY,
};
