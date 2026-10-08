import "./globals.css";

export const metadata = {
  title: "Factygo",
  description: "Evidence-first AI investigation platform",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
