import { Copy, Download } from "lucide-react";
import { useState } from "react";

const BANNER = { verified: "Verified", weak: "Weak evidence", failed: "Tests failed", inconclusive: "Inconclusive", not_run: "Not verified", no_patch: "No patch proposed" };

export default function ReportView({ report, name }) {
  const [copied, setCopied] = useState(false);
  function download() {
    const url = URL.createObjectURL(new Blob([report.markdown], { type: "text/markdown" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: `devpilot-${name.replace("/", "-")}.md` });
    a.click();
    URL.revokeObjectURL(url);
  }
  async function copy() {
    await navigator.clipboard.writeText(report.markdown);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }
  return (
    <>
      <div className={`banner v-${report.verdict}`}>
        <strong>{BANNER[report.verdict]}</strong>
        <span>{report.verdict_text}</span>
      </div>
      <div className="form-actions">
        <button className="ghost" onClick={copy}><Copy size={16} /> {copied ? "Copied" : "Copy PR summary"}</button>
        <button className="ghost" onClick={download}><Download size={16} /> Download .md</button>
      </div>
      <pre className="md">{report.markdown}</pre>
    </>
  );
}
