'use client';

import { createContext, useContext, useState, useEffect } from 'react';
import { useMsal, useIsAuthenticated } from "@azure/msal-react";
import { InteractionRequiredAuthError, InteractionStatus } from "@azure/msal-browser";
import { loginRequest } from './auth-config';
import { sessionUtils } from '../../components/session-timer';
import { rbaHelper } from './rba-helper';

const AuthContext = createContext({});

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const { instance, accounts, inProgress } = useMsal();
  const msalAuthenticated = useIsAuthenticated();
  const [department, setDepartment] = useState(null);

  const getAccessToken = async () => {
    const account = accounts[0];
    if (!account) {
      throw new Error('No account found');
    }

    try {
      const response = await instance.acquireTokenSilent({
        ...loginRequest,
        account,
      });
      return response.accessToken;
    } catch (error) {
      // Popup token acquisition breaks under Cross-Origin-Opener-Policy
      // (common in Opera / Chromium). Use redirect instead.
      if (error instanceof InteractionRequiredAuthError || error?.name === 'BrowserAuthError') {
        await instance.acquireTokenRedirect(loginRequest);
        return null;
      }
      console.error('Failed to get access token:', error);
      throw error;
    }
  };

  const getAuthHeaders = async () => {
    try {
      const token = await getAccessToken();
      if (!token) return {};
      return { 'Authorization': `Bearer ${token}` };
    } catch (error) {
      console.error('Failed to get auth headers:', error);
      return {};
    }
  };

  // Sync MSAL accounts → app user state
  useEffect(() => {
    if (inProgress !== InteractionStatus.None) {
      return;
    }

    const account = accounts[0];
    if (account) {
      const userData = {
        id: account.localAccountId,
        email: account.username,
        name: account.name,
        given_name: account.idTokenClaims?.given_name,
        family_name: account.idTokenClaims?.family_name,
        job_title: account.idTokenClaims?.jobTitle,
        tenant_id: account.tenantId,
        department: department
      };
      setUser(userData);

      if (!department) {
        rbaHelper.fetchUserDepartment(getAuthHeaders, setDepartment, setUser);
      }
      if (!sessionUtils.hasActiveSession()) {
        sessionUtils.startSession();
      }
    } else {
      setUser(null);
      setDepartment(null);
      sessionUtils.endSession();
    }
    setLoading(false);
  }, [accounts, department, inProgress]);

  const login = async () => {
    try {
      setLoading(true);
      setError(null);

      // Prefer silent SSO, then full-page redirect (no popup / COOP issues)
      if (accounts[0]) {
        try {
          await instance.acquireTokenSilent({
            ...loginRequest,
            account: accounts[0],
          });
          sessionUtils.startSession();
          setLoading(false);
          return;
        } catch {
          // fall through to redirect
        }
      }

      sessionUtils.startSession();
      await instance.loginRedirect(loginRequest);
      // Page navigates away; no need to clear loading
    } catch (error) {
      console.error('Login failed:', error);
      setError(error.message || 'Login failed');
      setLoading(false);
    }
  };

  const logout = async () => {
    try {
      setLoading(true);
      sessionUtils.endSession();
      setUser(null);
      setDepartment(null);
      await instance.logoutRedirect({
        postLogoutRedirectUri: typeof window !== 'undefined' ? window.location.origin : '/',
      });
    } catch (error) {
      console.error('Logout failed:', error);
      setError(error.message || 'Logout failed');
      setLoading(false);
    }
  };

  const isAuthenticated = () => {
    return !!user && (msalAuthenticated || accounts.length > 0);
  };

  const isAccounting = department === 'accounting';
  const isBanking = department === 'banking';
  const isAdmin = department === 'admin';

  const value = {
    user,
    loading: loading || inProgress !== InteractionStatus.None,
    error,
    login,
    logout,
    getAuthHeaders,
    getAccessToken,
    isAuthenticated,
    setError,
    department,
    isAccounting,
    isBanking,
    isAdmin
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};
