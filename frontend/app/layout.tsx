import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Criminal Law Q&A — Bangladesh",
  description:
    "Source-grounded question answering over the Code of Criminal Procedure, 1898. Legal information, not legal advice.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
