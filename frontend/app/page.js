"use client";

import { useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const tabs = [
  ["verdict", "Verdict"],
  ["evidence", "Web Evidence"],
  ["sources", "Sources"],
  ["claim", "Claim"],
  ["analysis", "Analysis"],
];

function label(v) {
  return String(v || "").replaceAll("_", " ").toUpperCase();
}

function verdictTone(v) {
  const x = String(v || "").toUpperCase();
  if (x === "TRUE") return "good";
  if (x === "FALSE") return "bad";
  if (x.includes("MOSTLY") || x === "PARTLY_TRUE") return "warn";
  return "neutral";
}

export default function Home() {
  const [text, setText] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState("verdict");

  async function investigate() {
    if (!text.trim()) return;
    setLoading(true);
    setResult(null);
    setTab("verdict");
    try {
      const response = await fetch(`${API}/api/investigate`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ text }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Investigation failed.");
      setResult(data);
    } catch (e) {
      setResult({ error: e.message || "Could not connect to Factygo API." });
    } finally {
      setLoading(false);
    }
  }

  const evidence = result?.evidence || [];
  const sources = result?.sources || [];
  const supporting = evidence.filter(e => String(e.stance).toLowerCase() === "supporting");
  const contradicting = evidence.filter(e => String(e.stance).toLowerCase() === "contradicting");
  const contextual = evidence.filter(e => String(e.stance).toLowerCase() === "contextual");

  return (
    <main className="shell">
      <header className="hero">
        <div>
          <div className="brand">FACTYGO</div>
          <h1>Evidence-first AI investigation</h1>
          <p>Research a claim and inspect the evidence behind the conclusion.</p>
        </div>
      </header>

      <section className="searchCard">
        <label htmlFor="claim">Investigate a claim</label>
        <textarea
          id="claim"
          value={text}
          onChange={e => setText(e.target.value)}
          placeholder="e.g. Is Congress the central government in India in 2026?"
          rows={4}
        />
        <div className="searchRow">
          <span className="hint">Text is enough. Attachments remain optional.</span>
          <button onClick={investigate} disabled={loading || !text.trim()}>
            {loading ? "Investigating…" : "Investigate"}
          </button>
        </div>
      </section>

      {result?.error && <section className="error">{result.error}</section>}

      {result && !result.error && (
        <section className="resultCard">
          <div className="resultHead">
            <div>
              <span className={`badge ${verdictTone(result.verdict)}`}>{label(result.verdict)}</span>
              <h2>{result.explanation || "Factygo completed the investigation."}</h2>
            </div>
            <div className="confidence">
              <strong>{result.confidence ?? 0}%</strong>
              <span>confidence</span>
            </div>
          </div>

          <nav className="tabs" aria-label="Investigation sections">
            {tabs.map(([id, name]) => (
              <button
                key={id}
                className={tab === id ? "active" : ""}
                onClick={() => setTab(id)}
              >
                {name}
                {id === "evidence" && <small>{evidence.length}</small>}
                {id === "sources" && <small>{sources.length}</small>}
              </button>
            ))}
          </nav>

          <div className="panel">
            {tab === "verdict" && (
              <div>
                <h3>Verdict</h3>
                <p className="lead">{result.explanation || "No explanation was returned."}</p>
                <div className="stats">
                  <div><b>{supporting.length}</b><span>Supporting</span></div>
                  <div><b>{contradicting.length}</b><span>Contradicting</span></div>
                  <div><b>{contextual.length}</b><span>Context</span></div>
                  <div><b>{sources.length}</b><span>Sources</span></div>
                </div>
                {result.status && <p className="muted">Investigation status: {label(result.status)}</p>}
              </div>
            )}

            {tab === "evidence" && (
              <div>
                <h3>Web Evidence</h3>
                {evidence.length ? evidence.map((e, i) => (
                  <article className="evidence" key={e.id || i}>
                    <div className="evidenceTop">
                      <span className={`stance ${String(e.stance).toLowerCase()}`}>{label(e.stance)}</span>
                      {e.relevance != null && <span>{e.relevance}% relevant</span>}
                      {e.strength != null && <span>{e.strength}% strength</span>}
                    </div>
                    <p>{e.excerpt}</p>
                    {e.reason && <small>{e.reason}</small>}
                    {e.source_url && <a href={e.source_url} target="_blank" rel="noreferrer">Open source ↗</a>}
                  </article>
                )) : <p className="muted">No sufficiently relevant web evidence was retrieved.</p>}
              </div>
            )}

            {tab === "sources" && (
              <div>
                <h3>Sources</h3>
                {sources.length ? sources.map((s, i) => (
                  <article className="source" key={s.url || i}>
                    <div>
                      <a href={s.url} target="_blank" rel="noreferrer">{s.title || s.url}</a>
                      <p>{s.domain || ""}</p>
                    </div>
                    <div className="sourceMeta">
                      {s.tier && <span>Tier {s.tier}</span>}
                      {s.quality != null && <span>{s.quality}/100</span>}
                    </div>
                  </article>
                )) : <p className="muted">No sources retrieved yet.</p>}
              </div>
            )}

            {tab === "claim" && (
              <div>
                <h3>Claim</h3>
                <div className="claimBox">{result.claim || text}</div>
                <h4>Claim breakdown</h4>
                {result.claims?.length ? (
                  <ol className="claims">{result.claims.map(c => <li key={c.id}>{c.text}</li>)}</ol>
                ) : <p className="muted">No additional claim decomposition was returned.</p>}
              </div>
            )}

            {tab === "analysis" && (
              <div>
                <h3>Analysis</h3>
                <div className="analysisGrid">
                  <div><span>Supporting</span><b>{supporting.length}</b></div>
                  <div><span>Contradicting</span><b>{contradicting.length}</b></div>
                  <div><span>Contextual</span><b>{contextual.length}</b></div>
                  <div><span>Independent domains</span><b>{new Set(sources.map(s => s.domain).filter(Boolean)).size}</b></div>
                </div>
                {result.methodology?.length > 0 && (
                  <>
                    <h4>Methodology</h4>
                    <ul className="method">{result.methodology.map((m, i) => <li key={i}>{m}</li>)}</ul>
                  </>
                )}
                <p className="muted">Detailed scoring and internal reasoning stay here so the main Verdict view remains focused.</p>
              </div>
            )}
          </div>
        </section>
      )}

      <footer>FACTYGO · Evidence-first investigation</footer>
    </main>
  );
}
