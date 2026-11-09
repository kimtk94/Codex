import "./globals.css";

export const metadata = {
  title: "CSS Automation",
  description: "CSS 업무 실행 및 Health Check"
};

export default function RootLayout({ children }) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
