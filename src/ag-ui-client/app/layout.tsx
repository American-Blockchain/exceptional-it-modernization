import "./globals.css";
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { CopilotKit } from "@copilotkit/react-core";
import "@copilotkit/react-ui/styles.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Agent Lightning: AG-UI CopilotKit",
  description: "Real-time visualization of Teacher/Student Agent Traces.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.className} bg-background text-foreground`}>
        {/* Opaque server-side proxy — internal Azure VNet redirects never reach the browser */}
        <CopilotKit runtimeUrl="/api/copilotkit" agent="mas_orchestrator">
          {children}
        </CopilotKit>
      </body>
    </html>
  );
}
