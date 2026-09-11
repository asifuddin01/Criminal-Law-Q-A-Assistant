"use client";

import { useCallback, useEffect, useState } from "react";
import { useRef } from "react";
import {
  API_URL,
  type AskResponse,
  type Meta,
  type ImageText,
  type Transcription,
  type Translation,
  type UploadedDocument,
} from "./types";

const EXAMPLES = [
  "When may a police officer arrest without a warrant?",
  "How long can police detain someone before a Magistrate?",
  "Is theft a bailable offence?",
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
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const recorder = useRef<MediaRecorder | null>(null);
  const [document_, setDocument] = useState<UploadedDocument | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileInput = useRef<HTMLInputElement | null>(null);
  const imageInput = useRef<HTMLInputElement | null>(null);
  const [reading, setReading] = useState(false);

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
          body: JSON.stringify({
            question: trimmed,
            language: "en",
            document_id: document_?.document_id ?? null,
          }),
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
    [busy, document_],
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

  // Offered only where the deployment can serve them. A control that fails on use
  // is worse than one that is absent.
  const features = meta?.features ?? ["text"];
  const canSpeak = features.includes("speech");
  const canRead = features.includes("image");

  const readImage = useCallback(async (file: File) => {
    setReading(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("image", file);
      const response = await fetch(`${API_URL}/api/image`, {
        method: "POST",
        body: form,
      });
      const body = await response.json();
      if (response.ok) {
        // Placed in the box for correction, not asked directly: an OCR slip would
        // otherwise become a wrong answer with no visible cause.
        setQuestion((body as ImageText).text);
      } else {
        setError(body?.detail ?? "No text could be read from that image.");
      }
    } catch {
      setError("Could not reach the image endpoint.");
    } finally {
      setReading(false);
      if (imageInput.current) imageInput.current.value = "";
    }
  }, []);

  const upload = useCallback(async (file: File) => {
    setUploading(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const response = await fetch(`${API_URL}/api/documents`, {
        method: "POST",
        body: form,
      });
      const body = await response.json();
      if (response.ok) {
        setDocument(body as UploadedDocument);
      } else {
        setError(body?.detail ?? "That file could not be read.");
      }
    } catch {
      setError("Could not reach the upload endpoint.");
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }, []);

  const stopRecording = useCallback(() => {
    recorder.current?.stop();
    recorder.current = null;
    setRecording(false);
  }, []);

  const startRecording = useCallback(async () => {
    setError(null);
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setError(
        "Microphone access was refused. Allow it in your browser, or type the question instead.",
      );
      return;
    }

    const chunks: BlobPart[] = [];
    const media = new MediaRecorder(stream);
    recorder.current = media;

    media.ondataavailable = (event) => {
      if (event.data.size) chunks.push(event.data);
    };

    media.onstop = async () => {
      stream.getTracks().forEach((track) => track.stop());
      const blob = new Blob(chunks, { type: media.mimeType || "audio/webm" });
      if (!blob.size) return;

      setTranscribing(true);
      try {
        const form = new FormData();
        form.append("audio", blob, "question.webm");
        const response = await fetch(`${API_URL}/api/transcribe`, {
          method: "POST",
          body: form,
        });
        const body = await response.json();
        if (response.ok) {
          // Shown for correction rather than asked straight away: a
          // mis-transcription would otherwise become a wrong answer with no
          // visible cause.
          setQuestion((body as Transcription).text);
        } else {
          setError(body?.detail ?? "Could not transcribe the recording.");
        }
      } catch {
        setError("Could not reach the transcription endpoint.");
      } finally {
        setTranscribing(false);
      }
    };

    media.start();
    setRecording(true);
  }, []);

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
          <button
            type="button"
            className="ghost"
            onClick={() => fileInput.current?.click()}
            disabled={uploading || busy}
            title="Attach a PDF or text file to ask about"
          >
            {uploading ? "Reading…" : "📎 Attach"}
          </button>
          <input
            ref={fileInput}
            type="file"
            accept=".pdf,.txt,.md,application/pdf,text/plain"
            hidden
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void upload(file);
            }}
          />
          {canRead && (
            <button
              type="button"
              className="ghost"
              onClick={() => imageInput.current?.click()}
              disabled={reading || busy}
              title="Photograph of an FIR, charge sheet or notice"
            >
              {reading ? "Reading image…" : "📷 Image"}
            </button>
          )}
          <input
            ref={imageInput}
            type="file"
            accept="image/*"
            hidden
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void readImage(file);
            }}
          />
          {canSpeak && (
            <button
              type="button"
              className={`ghost${recording ? " recording" : ""}`}
              onClick={() => (recording ? stopRecording() : void startRecording())}
              disabled={transcribing || busy}
              title="Ask aloud, in English or Bangla"
            >
              {transcribing
                ? "Transcribing…"
                : recording
                  ? "◼ Stop recording"
                  : "🎙 Speak"}
            </button>
          )}
          <span className="hint">
            ⌘/Ctrl + Enter
            {meta && ` · ${meta.provider.chat_model}`}
          </span>
        </div>
        {document_ && (
          <div className="attached">
            <div>
              <strong>{document_.filename}</strong>{" "}
              <span className="hint">
                {document_.pages} page{document_.pages === 1 ? "" : "s"},{" "}
                {document_.characters.toLocaleString()} characters
              </span>
              <p className="translation-notice" style={{ marginTop: 8 }}>
                {document_.notice}
              </p>
            </div>
            <button
              type="button"
              className="ghost"
              onClick={() => setDocument(null)}
            >
              Remove
            </button>
          </div>
        )}
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
                    <span className="cite-num">
                      {citation.source === "ScheduleII"
                        ? `Schedule II · Penal Code s.${citation.section}`
                        : `Section ${citation.section}`}
                    </span>
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
                        <strong>
                          {dropped.source === "ScheduleII"
                            ? `Schedule II, Penal Code s.${dropped.section}`
                            : `Section ${dropped.section}`}
                        </strong>{" "}
                        — {dropped.reason}
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
                    {result.retrieved_sections.map((section) => {
                      const [document, number] = section.includes(":")
                        ? section.split(":")
                        : ["CrPC", section];
                      return (
                        <span className="chip" key={section}>
                          {document === "ScheduleII" ? "Sch.II " : ""}s.{number}
                        </span>
                      );
                    })}
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
