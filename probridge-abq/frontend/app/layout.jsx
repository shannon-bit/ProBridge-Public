export const metadata = { title: "ProBridge ABQ" };

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body style={{margin:0,fontFamily:"system-ui"}}>
        <header style={{padding:"1rem",background:"#fff",borderBottom:"1px solid #ccc"}}>
          <div style={{fontWeight:700}}>ProBridge ABQ</div>
          <nav style={{display:"flex",gap:"1rem"}}>
            <a href="/">Home</a>
            <a href="/request">Request Help</a>
            <a href="/contractors">For Local Pros</a>
          </nav>
        </header>
        <main style={{padding:"1rem",maxWidth:"960px",margin:"0 auto"}}>{children}</main>
      </body>
    </html>
  );
}
