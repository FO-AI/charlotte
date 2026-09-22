import { PublicClientApplication, LogLevel } from "@azure/msal-browser";

const getRedirectUri = () => {
  if (typeof window !== "undefined") {
    return `${window.location.origin}/auth/callback`;
  }
  return process.env.NODE_ENV === "production"
    ? "https://charlotte-frontend.azurewebsites.net/auth/callback"
    : "http://localhost:3000/auth/callback";
};

// MSAL configuration — redirect flow avoids COOP/popup blockers (Opera, Chrome, etc.)
const msalConfig = {
  auth: {
    clientId: process.env.NEXT_PUBLIC_AZURE_AD_CLIENT_ID,
    authority: `https://login.microsoftonline.com/${process.env.NEXT_PUBLIC_AZURE_AD_TENANT_ID}`,
    redirectUri: getRedirectUri(),
    postLogoutRedirectUri:
      typeof window !== "undefined" ? window.location.origin : "/",
    navigateToLoginRequestUrl: false,
  },
  cache: {
    cacheLocation: "sessionStorage",
    storeAuthStateInCookie: false,
  },
  system: {
    loggerOptions: {
      logLevel: LogLevel.Warning,
    },
  },
};

export const loginRequest = {
  scopes: ["User.Read"],
};

export const msalInstance = new PublicClientApplication(msalConfig);

export default msalConfig;
