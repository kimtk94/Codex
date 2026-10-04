import "./globals.css";

export const metadata = {
  title: "MasterOS",
  description: "Research and CSS intelligence dashboard",
};

export default function RootLayout({ children }) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
