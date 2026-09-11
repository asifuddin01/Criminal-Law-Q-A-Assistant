"use client";

import { useCallback, useEffect, useState } from "react";
import {
  API_URL,
  type AskResponse,
  type Meta,
  type Translation,
} from "./types";

const EXAMPLES = [
  "When may a police officer arrest without a warrant?",
  "How long can police detain someone before a Magistrate?",
  "When may bail be granted for a non-bailable offence?",
  "পুলিশ কখন বিনা পরোয়ানায় গ্রেপ্তার করতে পারে?",
];

export default function Page() {
  const [question, setQuestion] = useState("");
  const [meta, setMeta] = useState<Meta | null>(null);
  const [result, setResult] = useState<AskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [translation, setTranslation] = useState<Translation | null>(null);
  const [translating, setTranslating] = useState(false);
  const [showTranslation, setShowTranslation] = useState(false);

  useEffect(() => {
    fetch(`${API_URL}/api/meta`)
      .then((r) => (r.ok ? r.json() : null))
      .then(setMeta)
      .catch(() => setMeta(null));
  }, []);

  const ask = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (trimmed.length < 3 || busy) return;

      setBusy(true);
      setError(null);
      setResult(null);
      setTranslation(null);
      setShowTranslation(false);
      try {
        const response = await fetch(`${API_URL}/api/ask`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question: trimmed, language: "en" }),
        });
        const body = await response.json();
        if (!response.ok) {
          setError(body?.detail ?? `Request failed (${response.status})`);
        } else {
          setResult(body as AskResponse);
        }
      } catch {
        setError(
          `Could not reach the API at ${API_URL}. Is the backend running?`,
        );
      } finally {
        setBusy(false);
      }
    },
    [busy],
  );

  const toggleTranslation = useCallback(async () => {
    if (!result) return;
    if (translation) {
      setShowTranslation((shown) => !shown);
      return;
    }

    setTranslating(true);
    try {
      const response = await fetch(`${API_URL}/api/translate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: result.refused ? result.reason || result.answer : result.answer,
          target: "bn",
        }),
      });
      const body = await response.json();
      if (response.ok) {
        setTranslation(body as Translation);
        setShowTranslation(true);
      } else {
        setError(body?.detail ?? "Translation failed");
      }
    } catch {
      setError("Could not reach the translation endpoint.");
    } finally {
      setTranslating(false);
    }
  }, [result, translation]);

  const disclaimer = result?.disclaimer ?? meta?.disclaimer;

  return (
    <main className="shell">
      <header>
        <h1>Criminal Law Q&amp;A — Bangladesh</h1>
        <p className="sub">
          The Code of Criminal Procedure, 1898 (Act No. V of 1898). Every answer
          is grounded in retrieved statutory text, and every citation is checked
          against the source before it is shown.
        </p>
      </header>

      {disclaimer && <div className="disclaimer">{disclaimer}</div>}

      <form
        onSubmit={(event) => {
          event.preventDefault();
          void ask(question);
        }}
      >
        <textarea
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Ask about arrest, bail, investigation, trial procedure… English or বাংলা"
          onKeyDown={(event) => {
            if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
              event.preventDefault();
              void ask(question);
            }
          }}
        />
        <div className="controls">
          <button type="submit" disabled={busy || question.trim().length < 3}>
            {busy ? "Searching the Code…" : "Ask"}
          </button>
          <span className="hint">
            ⌘/Ctrl + Enter
            {meta && ` · ${meta.provider.chat_model}`}
          </span>
        </div>
        <div className="examples">
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => {
                setQuestion(example);
                void ask(example);
              }}
            >
              {example.length > 46 ? `${example.slice(0, 46)}…` : example}
            </button>
          ))}
        </div>
      </form>

      {error && <div className="error">{error}</div>}

      {result && (
        <>
          <section className={`panel${result.refused ? " refused" : ""}`}>
            <div className="panel-head">
              <h2>{result.refused ? "No answer given" : "Answer"}</h2>
              <button
                type="button"
                className="ghost"
                onClick={() => void toggleTranslation()}
                disabled={translating}
              >
                {translating
                  ? "অনুবাদ হচ্ছে…"
                  : showTranslation
                    ? "Show in English"
                    : "বাংলায় দেখুন"}
              </button>
            </div>
            <div className={`answer${showTranslation ? " bn" : ""}`}>
              {showTranslation && translation
                ? translation.text
                : result.refused
                  ? result.reason || result.answer
                  : result.answer}
            </div>
            {showTranslation && translation && (
              <p className="translation-notice">{translation.notice}</p>
            )}
          </section>

          {result.citations.length > 0 && (
            <section className="panel">
              <h2>
                Citations — {result.citations.length} verified against the source
                {showTranslation && " · quoted text stays in English"}
              </h2>
              {result.citations.map((citation) => (
                <article className="cite" key={`${citation.section}-${citation.quote}`}>
                  <div className="cite-head">
                    <span className="cite-num">Section {citation.section}</span>
                    <span className="cite-note">{citation.marginal_note}</span>
                    <span
                      className={`badge ${citation.quote_verified ? "ok" : "no"}`}
                    >
                      {citation.quote_verified
                        ? "quote verified"
                        : "no verified quote"}
                    </span>
                  </div>
                  {(citation.part || citation.chapter) && (
                    <div className="cite-path">
                      {[citation.part, citation.chapter]
                        .filter(Boolean)
                        .join(" › ")}
                    </div>
                  )}
                  {citation.quote && <blockquote>{citation.quote}</blockquote>}
                  <a
                    href={citation.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Read section {citation.section} on bdlaws.minlaw.gov.bd →
                  </a>
                </article>
              ))}
            </section>
          )}

          {(result.dropped_citations.length > 0 ||
            result.retrieved_sections.length > 0) && (
            <section className="panel">
              <h2>How this answer was checked</h2>

              {result.dropped_citations.length > 0 ? (
                <details open>
                  <summary>
                    {result.dropped_citations.length} citation
                    {result.dropped_citations.length === 1 ? "" : "s"} withheld —
                    the system would not stand behind them
                  </summary>
                  <ul>
                    {result.dropped_citations.map((dropped, index) => (
                      <li key={index}>
                        <strong>Section {dropped.section}</strong> —{" "}
                        {dropped.reason}
                        {dropped.quote && (
                          <>
                            {" "}
                            <em>“{dropped.quote}”</em>
                          </>
                        )}
                      </li>
                    ))}
                  </ul>
                </details>
              ) : (
                <p className="hint" style={{ margin: 0 }}>
                  Nothing was withheld — every citation the model produced
                  resolved to a retrieved section.
                </p>
              )}

              {result.retrieved_sections.length > 0 && (
                <details>
                  <summary>
                    Sections retrieved and put in front of the model (
                    {result.retrieved_sections.length})
                  </summary>
                  <div className="chips">
                    {result.retrieved_sections.map((section) => (
                      <span className="chip" key={section}>
                        s.{section}
                      </span>
                    ))}
                  </div>
                </details>
              )}
            </section>
          )}
        </>
      )}

      <footer>
        Statutory text reproduced from{" "}
        <a
          href="https://bdlaws.minlaw.gov.bd"
          target="_blank"
          rel="noopener noreferrer"
        >
          bdlaws.minlaw.gov.bd
        </a>
        , published by the Legislative and Parliamentary Affairs Division,
        Ministry of Law, Justice and Parliamentary Affairs.
        {meta && ` · ${meta.app_name} v${meta.version}`}
      </footer>
    </main>
  );
}
