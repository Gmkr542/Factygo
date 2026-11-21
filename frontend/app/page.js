"use client";

import { useEffect, useMemo, useRef, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const tabs = [
  ["verdict", "Verdict"],
  ["evidence", "Web Evidence"],
  ["sources", "Sources"],
  ["claim", "Claim"],
  ["analysis", "Analysis"],
  ["research", "Research"],
];

const SAMPLE_PROMPTS = [
  { text: "Lemon juice reduces diabetes", tag: "Health" },
  { text: "Drinking green tea prevents heart disease", tag: "Medical" },
  { text: "India's Chandrayaan-3 landed near the lunar south pole in August 2023", tag: "Space" },
  { text: "The Great Wall of China is visible from the Moon with the naked eye", tag: "Science" },
  { text: "Does intermittent fasting improve insulin sensitivity?", tag: "Question" },
  { text: "Antibiotics are effective against viral infections like the common cold", tag: "Medical" },
  { text: "Does India have the world's largest population?", tag: "Question" },
  { text: "Solar panels generate zero electricity on cloudy days", tag: "Energy" },
];

function label(value) {
  return String(value || "").replaceAll("_", " ").toUpperCase();
}

function verdictTone(value) {
  const x = String(value || "").toUpperCase();
  if (x === "TRUE") return "good";
  if (x === "FALSE") return "bad";
  if (x.includes("MOSTLY") || x === "PARTLY_TRUE" || x === "PARTLY TRUE" || x === "MISLEADING") return "warn";
  return "neutral";
}

function confidenceTone(value) {
  const n = Number(value || 0);
  if (n >= 75) return "high";
  if (n >= 45) return "medium";
  return "low";
}

function splitReport(explanation) {
  const raw = String(explanation || "").trim();
  if (!raw) {
    return {
      summary: "Factygo completed the investigation.",
      breakdown: "No detailed breakdown was returned.",
    };
  }
  const idx = raw.indexOf("Breakdown:");
  if (idx !== -1) {
    const summary = raw.slice(0, idx).trim();
    const breakdown = raw.slice(idx).trim();
    return {
      summary: summary || raw,
      breakdown: breakdown || raw,
    };
  }
  const sentences = raw.split(/(?<=[.!?])\s+/).filter(Boolean);
  if (sentences.length >= 2) {
    return {
      summary: sentences[0],
      breakdown: "Breakdown: " + sentences.slice(1).join(" "),
    };
  }
  return {
    summary: raw,
    breakdown: raw,
  };
}

export default function Home() {
  const [text, setText] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState("verdict");
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [shuffledPrompts, setShuffledPrompts] = useState(SAMPLE_PROMPTS);
  const searchBoxRef = useRef(null);

  function shuffleSuggestions() {
    const copy = [...SAMPLE_PROMPTS];
    for (let i = copy.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [copy[i], copy[j]] = [copy[j], copy[i]];
    }
    setShuffledPrompts(copy);
  }

  useEffect(() => {
    function handleOutsideClick(e) {
      if (searchBoxRef.current && !searchBoxRef.current.contains(e.target)) {
        setShowSuggestions(false);
      }
    }
    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, []);

  const filteredSuggestions = useMemo(() => {
    const q = text.trim().toLowerCase();
    if (!q) return shuffledPrompts;
    const matches = shuffledPrompts.filter(item => item.text.toLowerCase().includes(q));
    return matches.length >= 3
      ? matches
      : [...matches, ...shuffledPrompts.filter(item => !item.text.toLowerCase().includes(q))];
  }, [text, shuffledPrompts]);

  async function investigate(overrideText) {
    const claim = (typeof overrideText === "string" ? overrideText : text).trim();
    if (!claim) return;

    setShowSuggestions(false);
    setLoading(true);
    setResult(null);
    setTab("verdict");

    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 45000);
      let response;
      try {
        response = await fetch(API + "/api/investigate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: claim }),
          signal: controller.signal,
        });
      } finally {
        clearTimeout(timer);
      }
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Investigation failed.");
      setResult(data);
    } catch (error) {
      setResult({
        error:
          error.name === "AbortError"
            ? "Research timed out. The web search provider may be unavailable right now."
            : error.message || "Could not connect to Factygo API.",
      });
    } finally {
      setLoading(false);
    }
  }

  const evidence = result?.evidence || [];
  const sources = result?.sources || [];
  const supporting = useMemo(
    () => evidence.filter(e => String(e.stance).toLowerCase() === "supporting"),
    [evidence]
  );
  const contradicting = useMemo(
    () => evidence.filter(e => String(e.stance).toLowerCase() === "contradicting"),
    [evidence]
  );
  const contextual = useMemo(
    () => evidence.filter(e => String(e.stance).toLowerCase() === "contextual"),
    [evidence]
  );
  const domains = useMemo(() => {
    if (result?.evidence_analysis?.independent_domains != null && result.evidence_analysis.independent_domains > 0) {
      return result.evidence_analysis.independent_domains;
    }
    const hosts = new Set(
      sources
        .map(s => {
          if (s.domain) return s.domain;
          try {
            return new URL(s.url).hostname.replace(/^www\./, "");
          } catch {
            return "";
          }
        })
        .filter(Boolean)
    );
    return hosts.size;
  }, [result, sources]);

  const confidence = Number(result?.confidence || 0);
  const noResults = result && !result.error && !evidence.length && !sources.length;
  const { summary, breakdown } = useMemo(() => splitReport(result?.explanation), [result?.explanation]);

  return (
    <main className="appShell">
      <div className="topBar">
        <div className="brandMark"><span className="brandDot" />FACTYGO</div>
        <span className="topTag">EVIDENCE-FIRST INVESTIGATION</span>
      </div>

      <header className="hero">
        <div className="eyebrow">AI RESEARCH WORKSPACE</div>
        <h1>Investigate claims.<br /><span>Follow the evidence.</span></h1>
        <p>Research a claim across the web, inspect the evidence, and see how the conclusion was reached.</p>
      </header>

      <section className="searchCard" ref={searchBoxRef}>
        <div className="searchLabelRow">
          <label htmlFor="claim">What do you want to investigate?</label>
          <span>TEXT INPUT</span>
        </div>
        <div className="inputWrap">
          <textarea
            id="claim"
            value={text}
            onFocus={() => {
              shuffleSuggestions();
              setShowSuggestions(true);
            }}
            onKeyUp={e => {
              if (e.key === "Escape") {
                setShowSuggestions(false);
                return;
              }
              if (!(e.ctrlKey || e.metaKey) && e.key !== "Enter") {
                setShowSuggestions(true);
              }
            }}
            onChange={e => setText(e.target.value)}
            onKeyDown={e => {
              if ((e.ctrlKey || e.metaKey) && e.key === "Enter") investigate();
            }}
            placeholder="Write your claim or question..."
            rows={2}
            disabled={loading}
          />
          {showSuggestions && !loading && (
            <div className="suggestionsDropdown" role="listbox" aria-label="Suggested claims and questions">
              <div className="suggestionsHeader">
                <span>SUGGESTED CLAIMS & QUESTIONS</span>
                <span>SCROLL FOR MORE</span>
              </div>
              <div className="suggestionsList">
                {filteredSuggestions.map((item, idx) => (
                  <button
                    type="button"
                    key={item.text + "-" + idx}
                    className="suggestionItem"
                    onClick={() => {
                      setText(item.text);
                      setShowSuggestions(false);
                    }}
                  >
                    <span>{item.text}</span>
                    <span className="suggestionTag">{item.tag}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
        <div className="searchFooter">
          <span className="hint">Attachments are optional · Ctrl/Cmd + Enter to investigate</span>
          <button className="primaryButton" onClick={() => investigate()} disabled={loading || !text.trim()}>
            {loading ? <><span className="spinner" /> Researching…</> : <>Investigate <span>→</span></>}
          </button>
        </div>
      </section>

      {loading && (
        <section className="loadingCard">
          <div className="loadingIcon"><span className="spinner dark" /></div>
          <div>
            <strong>Investigating claim</strong>
            <p>Searching the web and evaluating available evidence…</p>
          </div>
        </section>
      )}

      {result?.error && (
        <section className="stateCard errorState">
          <div className="stateIcon">!</div>
          <div>
            <strong>Investigation failed</strong>
            <p>{result.error}</p>
            <button className="secondaryButton" onClick={() => investigate()}>Try again</button>
          </div>
        </section>
      )}

      {result && !result.error && (
        <section className="investigationCard">
          <div className="resultHero">
            <div className="verdictBlock">
Use code with caution.
<div className={"verdictBadge " + verdictTone(result.verdict)}>

{label(result.verdict)}

{summary}

{label(result.status || "complete")}
•
{domains} independent {domains === 1 ? "domain" : "domains"}


<div className={"confidenceMeter " + confidenceTone(confidence)}>
<div className="confidenceRing" style={{ "--confidence": confidence + "%" }}>
{confidence}%

CONFIDENCE

{tabs.map(([id, name]) => (
<button
key={id}
className={tab === id ? "active" : ""}
onClick={() => setTab(id)}
>
{name}
{id === "evidence" ? " (" + evidence.length + ")" : ""}
{id === "sources" ? " (" + sources.length + ")" : ""}

))}
{tab === "verdict" && (



CONCLUSION
Verdict Breakdown

{noResults ? (

?
No sufficiently relevant evidence
Factygo could not retrieve enough reliable web evidence to determine whether this claim is true or false. It will not invent a verdict.
<button className="secondaryButton" onClick={() => investigate()}>Search again

) : (
<>
{breakdown}

SUPPORTING{supporting.length}
CONTRADICTING{contradicting.length}
CONTEXT{contextual.length}
SOURCES{sources.length}


i

Evidence overview

{supporting.length
? supporting.length + " supporting item" + (supporting.length === 1 ? "" : "s") + " found."
: "No direct supporting evidence found."}{" "}
{contradicting.length
? contradicting.length + " contradiction" + (contradicting.length === 1 ? "" : "s") + " detected."
: "No direct contradiction detected."}



</>
)}

)}
{tab === "evidence" && (


WEB RESEARCHEvidence
{evidence.length} items

{evidence.length ? (

{evidence.map((e, i) => (
<article className="evidenceCard" key={e.id || i}>

<span className={"stance " + String(e.stance).toLowerCase()}>{label(e.stance)}

{e.relevance != null && Relevance {e.relevance}%}
{e.strength != null && Strength {e.strength}%}


“{e.excerpt}”
{e.reason && {e.reason}}
{e.source_url && Open original source ↗}

))}

) : (
⌕No web evidenceNo sufficiently relevant evidence was retrieved.
)}

)}
{tab === "sources" && (


WEB RESEARCHSources
{sources.length} sources

{sources.length ? (

{sources.map((s, i) => {
let displayDomain = s.domain || "";
if (!displayDomain && s.url) {
try {
displayDomain = new URL(s.url).hostname.replace(/^www./, "");
} catch {
displayDomain = "Unknown domain";
}
}
return (
<article className="sourceCard" key={s.url || i}>
↗

{s.title || s.url}
{displayDomain || "Unknown domain"}


{s.source_tier && Tier {s.source_tier}}
{s.source_score != null && {Math.round(s.source_score * 100)}/100}


);
})}

) : (
◎No sources retrievedFactygo has no sources to display for this investigation.
)}

)}
{tab === "claim" && (

CLAIM UNDERSTANDING
Claim
{result.claim || text}
{result.claim_analysis && (

SUBJECT{result.claim_analysis.subject || "Unknown"}
JURISDICTION{result.claim_analysis.jurisdiction || "Unknown"}
YEAR{result.claim_analysis.year || "Not specified"}
TYPE{label(result.claim_analysis.claim_type || "Unknown")}

)}
Claim breakdown
{result.claims?.length ? {result.claims.map(c => {c.text})} : No additional decomposition returned.}

)}
{tab === "research" && (

RESEARCH PLAN
Framed questions
Each question is researched independently. These raw answers are evidence inputs for the final synthesis, not separate verdicts.

{(result.research_questions || []).map((q) => (


Q{q.id}
{q.evidence_count} source{q.evidence_count === 1 ? "" : "s"}{label(q.status)}

{q.question}
{q.raw_answer || "No raw answer returned."}
{q.sources?.length > 0 && {q.sources.map((source) => {source.title || source.domain} ↗)}}

))}


)}
{tab === "analysis" && (

INVESTIGATION INTELLIGENCE
Analysis

SUPPORTING{supporting.length}
CONTRADICTING{contradicting.length}
CONTEXTUAL{contextual.length}
INDEPENDENT DOMAINS{domains}

{result.evidence_analysis && (

Corroboration
{result.evidence_analysis.supporting_domains?.length || 0} supporting domains · {result.evidence_analysis.contradicting_domains?.length || 0} contradicting domains

)}
{result.methodology?.length > 0 && <>Methodology{result.methodology.map((m, i) => {m})}</>}

)}

)}
FACTYGO · Evidence-first AI investigation · Evidence over assumption

);
}
