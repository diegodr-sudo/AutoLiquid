import type { Metadata } from 'next'
import { Analytics } from '@vercel/analytics/next'
import { ThemeProvider } from '@/components/theme-provider'
import { ThemeIconSync } from '@/components/theme-icon-sync'
import { AppThemeSync } from '@/components/app-theme-sync'
import { PlatformSync } from '@/components/platform-sync'
import { Toaster } from '@/components/ui/toaster'
import { AuthProvider } from '@/lib/auth-context'
import './globals.css'

export const metadata: Metadata = {
  title: 'AutoLiquid · Automação de Liquidação',
  description: 'AutoLiquid — Sistema de automação contábil para processamento de notas fiscais no Comprasnet / SIAFI',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="pt-BR" suppressHydrationWarning>
      <body className="font-sans antialiased">
        <ThemeProvider attribute="class" defaultTheme="light" enableSystem disableTransitionOnChange>
          <AuthProvider>
            <AppThemeSync />
            <ThemeIconSync />
            <PlatformSync />
            {children}
            <Toaster />
            {process.env.NODE_ENV === 'production' && <Analytics />}
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  )
}
