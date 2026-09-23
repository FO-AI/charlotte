import './globals.css';
import localFont from 'next/font/local';
import MsalProviderWrapper from '../lib/auth/msal-provider-wrapper';

const openSans = localFont({
  src: [
    {
      path: '../public/fonts/OpenSans-Regular.woff2',
      weight: '400',
      style: 'normal',
    },
    {
      path: '../public/fonts/OpenSans-Bold.woff2',
      weight: '700',
      style: 'normal',
    },
  ],
  display: 'swap',
  fallback: ['Arial', 'Helvetica', 'sans-serif'],
  variable: '--font-open-sans',
});

export const metadata = {
  title: {
    default: 'Charlotte | Finance and Operations',
    template: '%s | Charlotte | Finance and Operations',
  },
  description:
    'Internal AI workspace for UNC Finance and Operations employees.',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body className={openSans.className}>
        <MsalProviderWrapper>
          {children}
        </MsalProviderWrapper>
      </body>
    </html>
  );
}
