"use client";

import { useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Home() {
  const [text, setText] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  async function investigate() {
    if (!text.trim()) return;
    setLoading(true);
    setResult(null);
    try {
      const response = await fetch(`${API}/api/investigate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      const data = await response.json();
      setResult(response.ok ? data : { error: data.detail || "Investigation failed." });
    } catch {
      setResult({ error: "Could not connect to Factygo API." });
    } finally {
      setLoading(false);
    }
  }

  return (
    <main style={{ maxWidth: 1000, margin: "0 auto", padding: "50px 24px", fontFamily: "Arial, sans-serif" }}>
      <div style={{ marginBottom: 35 }}>
        <h1 style={{ fontSize: 42, marginBottom: 8 }}>Factygo</h1>
        <p style={{ fontSize: 18 }}>Evidence-first AI investigation</p>
      </div>

      <section style={{ background: "white", padding: 24, borderRadius: 14, boxShadow: "0 2px 12px rgba(0,0,0,.06)" }}>
        <h2>Investigate a claim</h2>
        <textarea
          value={text}
          onChange={e => setText(e.target.value)}
          placeholder="Paste a claim, post, or statement..."
          rows={7}
          style={{ width: "100%", padding: 14, boxSizing: "border-box", borderRadius: 8, border: "1px solid #ccc" }}
        />
        <button onClick={investigate} disabled={loading} style={{ marginTop: 14, padding: "12px 22px", borderRadius: 8 }}>
          {loading ? "Investigating..." : "Investigate"}
        </button>
      </section>

      {result && !result.error && (
        <section style={{ marginTop: 24, background: "white", padding: 24, borderRadius: 14, boxShadow: "0 2px 12px rgba(0,0,0,.06)" }}>
          <h2>{result.verdict}</h2>
          <p><b>Confidence:</b> {result.confidence}%</p>
          <p>{result.explanation}</p>

          <h3>Claim breakdown</h3>
          <ol>{result.claims?.map(c => <li key={c.id}>{c.text}</li>)}</ol>

          <h3>Evidence assessment</h3>
          <p>
            Supporting: <b>{result.analysis?.supporting_count ?? 0}</b> ·
            Contradicting: <b>{result.analysis?.contradicting_count ?? 0}</b> ·
            Contextual: <b>{result.analysis?.contextual_count ?? 0}</b>
          </p>
          {result.analysis?.supporting_domains?.length > 0 && (
            <p><b>Supporting domains:</b> {result.analysis.supporting_domains.join(", ")}</p>
          )}
          {result.analysis?.contradicting_domains?.length > 0 && (
            <p><b>Contradicting domains:</b> {result.analysis.contradicting_domains.join(", ")}</p>
          )}

          <h3>Sources</h3>
          {result.sources?.length ? result.sources.map((s, i) => (
            <p key={i}>
              <a href={s.url} target="_blank" rel="noreferrer">{s.title}</a>
              <br />
              <small>Tier {s.source_tier} · {s.source_type} · quality {Math.round(s.source_score * 100)}/100 · {s.domain}</small>
            </p>
          )) : <p>No sources retrieved yet.</p>}

          <h3>Evidence</h3>
          {result.evidence?.length ? result.evidence.map((e, i) => (
            <article key={i} style={{ borderTop: "1px solid #ddd", padding: "14px 0" }}>
              <b>{e.stance.toUpperCase()}</b> · relevance {Math.round(e.relevance * 100)}% · strength {Math.round(e.strength * 100)}%
              <p>{e.excerpt}</p>
              <small>{e.rationale} · {e.domain} · Tier {e.source_tier}</small>
            </article>
          )) : <p>Factygo will not invent evidence.</p>}

          <h3>Methodology</h3>
          <ul>{result.methodology?.map((m, i) => <li key={i}>{m}</li>)}</ul>
        </section>
      )}

      {result?.error && <p style={{ marginTop: 20 }}>{result.error}</p>}
    </main>
  );
}
