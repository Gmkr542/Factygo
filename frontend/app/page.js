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
      setResult(data);
    } catch (error) {
      setResult({ error: "Could not connect to Factygo API." });
    } finally {
      setLoading(false);
    }
  }

  return (
    <main style={{ maxWidth: 900, margin: "50px auto", padding: 24 }}>
      <h1>Factygo</h1>
      <p>Evidence-first AI investigation</p>

      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Paste a claim or social-media post..."
        rows={7}
        style={{ width: "100%", padding: 14, boxSizing: "border-box" }}
      />

      <button
        onClick={investigate}
        disabled={loading}
        style={{ marginTop: 14, padding: "12px 20px", cursor: "pointer" }}
      >
        {loading ? "Investigating..." : "Investigate"}
      </button>

      {result && (
        <section style={{ marginTop: 30 }}>
          {result.error ? (
            <p>{result.error}</p>
          ) : (
            <>
              <h2>{result.verdict}</h2>
              <p><b>Confidence:</b> {result.confidence}%</p>
              <p>{result.explanation}</p>

              <h3>Claim breakdown</h3>
              <ul>
                {result.claims?.map((claim) => (
                  <li key={claim.id}>{claim.text}</li>
                ))}
              </ul>

              <h3>Evidence</h3>
              {result.evidence?.length ? (
                result.evidence.map((item, i) => (
                  <article key={i}>
                    <b>{item.title}</b>
                    <p>{item.excerpt}</p>
                    <a href={item.url} target="_blank">Source</a>
                  </article>
                ))
              ) : (
                <p>No evidence retrieved yet. Factygo will not invent sources.</p>
              )}
            </>
          )}
        </section>
      )}
    </main>
  );
}
