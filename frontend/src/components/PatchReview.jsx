import { useMemo, useState } from "react";
import { ShieldCheck, ThumbsDown } from "lucide-react";
import Tag from "./Tag.jsx";

function sideBySide(diff) {
  const rows = [];
  let del = [], add = [];
  const flush = () => {
    const n = Math.max(del.length, add.length);
    for (let i = 0; i < n; i++) rows.push({ l: del[i], r: add[i], type: "chg" });
    del = []; add = [];
  };
  for (const line of diff.split("\n")) {
    if (line.startsWith("---") || line.startsWith("+++")) continue;
    if (line.startsWith("@@")) { flush(); rows.push({ hunk: line }); }
    else if (line.startsWith("-")) del.push(line.slice(1));
    else if (line.startsWith("+")) add.push(line.slice(1));
    else if (line.length || del.length || add.length) { flush(); rows.push({ l: line.slice(1), r: line.slice(1), type: "ctx" }); }
  }
  flush();
  return rows;
}

export default function PatchReview({ data, status, onDecide, busy }) {
  const [mode, setMode] = useState("split");
  const [note, setNote] = useState("");
  const { patch, test } = data;
  const rows = useMemo(() => sideBySide(patch.unified_diff), [patch.unified_diff]);

  return (
    <>
      <div className="patch-head">
        <div>
          <h3>{patch.finding_title}</h3>
          <code>{patch.file}</code>
        </div>
        <Tag kind={patch.source === "rule" ? "rule" : "llm"} />
      </div>
      <p>{patch.explanation}</p>
      {patch.source === "llm" && <p className="note">This patch was written by a language model. Treat it as a suggestion until the test result says otherwise.</p>}
      <div className="seg" role="group" aria-label="Diff layout">
        <button className={mode === "split" ? "on" : ""} onClick={() => setMode("split")}>Side by side</button>
        <button className={mode === "unified" ? "on" : ""} onClick={() => setMode("unified")}>Unified</button>
        <span className="stat">+{patch.validation.lines_added} / −{patch.validation.lines_removed}</span>
      </div>
      {mode === "split" ? (
        <div className="diff split" role="table" aria-label="Original and proposed code">
          <div className="diff-cols"><span>Original</span><span>Proposed</span></div>
          {rows.map((r, i) =>
            r.hunk ? <div key={i} className="hunk">{r.hunk}</div> : (
              <div key={i} className={`drow ${r.type}`}>
                <pre className={r.l !== undefined && r.type === "chg" ? "del" : ""}>{r.l ?? ""}</pre>
                <pre className={r.r !== undefined && r.type === "chg" ? "add" : ""}>{r.r ?? ""}</pre>
              </div>
            )
          )}
        </div>
      ) : (
        <pre className="diff unified">
          {patch.unified_diff.split("\n").map((l, i) => (
            <span key={i} className={l.startsWith("+") && !l.startsWith("+++") ? "add" : l.startsWith("-") && !l.startsWith("---") ? "del" : l.startsWith("@@") ? "hunk" : ""}>{l + "\n"}</span>
          ))}
        </pre>
      )}

      {test && (
        <>
          <h3>Test that will run</h3>
          <p className="note"><strong>Strength:</strong> {test.strength}</p>
          <pre className="code">{test.code}</pre>
        </>
      )}

      {status === "awaiting_approval" && (
        <div className="approval">
          <h3>Your decision</h3>
          <p>Approving runs the test twice inside a network-less container: once on the original code, once on the patched code. Nothing is sent to GitHub.</p>
          <label htmlFor="note">Note (optional)</label>
          <input id="note" value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} />
          <div className="form-actions">
            <button className="primary" disabled={busy} onClick={() => onDecide(true, note)}><ShieldCheck size={16} /> Approve and run tests</button>
            <button className="ghost" disabled={busy} onClick={() => onDecide(false, note)}><ThumbsDown size={16} /> Reject</button>
          </div>
        </div>
      )}
      {data.approval && <p className="note">{data.approval.approved ? "Approved" : "Rejected"} {new Date(data.approval.at).toLocaleString()}{data.approval.note ? `: ${data.approval.note}` : ""}</p>}
    </>
  );
}
