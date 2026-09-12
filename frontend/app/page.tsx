"use client";

import { useCallback, useEffect, useState } from "react";
import { useRef } from "react";
import {
  API_URL,
  type Amendment,
  type AskResponse,
  type Citation,
  type Meta,
  type ImageText,
  type Offence,
  type Transcription,
  type Translation,
  type UploadedDocument,
} from "./types";

/** "10 August 2025" — the form a date takes in a statute, not a locale default. */
function formatDate(iso: string): string {
  const parsed = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}

/**
 * What the collapsed row says. The most recent effective date is the fact that
 * decides whether this section governs the matter being asked about, so it goes
 * in the summary rather than behind the disclosure triangle.
 */
function amendmentSummary(amendments: Amendment[]): string {
  const count = amendments.length;
  const label = count === 1 ? "1 amendment" : `${count} amendments`;
  const latest = amendments.find((a) => a.effective_from);
  return latest
    ? `${label} — most recently in force from ${formatDate(latest.effective_from!)}`
    : `${label} — no effective date stated`;
}

/**
 * One card per cited section, not per quotation.
 *
 * A long section is split into several chunks, so the model can verify two or
 * three separate excerpts from the same provision. Rendered one card each, the
 * list repeats the section heading, the part and chapter path, the bdlaws link
 * and the whole amendment history identically for each — and "3 citations" reads
 * as three provisions when it is one. A lawyer reads in sections; the excerpts
 * are the evidence under a section, not peers of it.
 */
interface CitedSection {
  key: string;
  section: string;
  source: string;
  marginal_note: string;
  part: string | null;
  chapter: string | null;
  source_url: string;
  amendments: Amendment[];
  offence: Offence | null;
  quotes: string[];
  verified: number;
}

/**
 * A Schedule II column, in words.
 *
 * "depends" is the schedule's own answer, not a gap in the parse: many rows read
 * "according as the offence abetted is bailable or not". Printing it as "No"
 * would be a wrong answer where the table declines to give one.
 */
const OFFENCE_VALUE: Record<string, string> = {
  yes: "Yes",
  no: "No",
  depends: "Depends on the underlying offence",
  unknown: "Not stated in the schedule",
};

function groupBySection(citations: Citation[]): CitedSection[] {
  const bySection = new Map<string, CitedSection>();
  for (const c of citations) {
    const key = `${c.source}:${c.section}`;
    let entry = bySection.get(key);
    if (!entry) {
      entry = {
        key,
        section: c.section,
        source: c.source,
        marginal_note: c.marginal_note,
        part: c.part,
        chapter: c.chapter,
        source_url: c.source_url,
        amendments: c.amendments ?? [],
        offence: c.offence ?? null,
        quotes: [],
        verified: 0,
      };
      bySection.set(key, entry);
    }
    if (!entry.offence && c.offence) entry.offence = c.offence;
    if (c.quote && !entry.quotes.includes(c.quote)) entry.quotes.push(c.quote);
    if (c.quote_verified) entry.verified += 1;
  }
  return [...bySection.values()];
}

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
  // Which model answers. Null means the deployment's default, until /api/meta
  // says what is actually available — a hosted deployment usually has no local
  // model, and the control must not offer one that is not there.
  const [provider, setProvider] = useState<string | null>(null);
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
            provider,
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
    // `provider` belongs here. Without it the callback closes over the value at
    // the time it was created, and the request goes to whichever model was
    // selected when the page loaded — the toggle moves, the label updates, and
    // the question is still answered by the old model.
    [busy, document_, provider],
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

  const activeModel =
    meta?.providers?.find((p) => p.name === provider)?.model ??
    meta?.provider.chat_model;

  // Why a model in the toggle is greyed out. The deployment says so — on a Space
  // the local model is being fetched rather than missing, and the difference is
  // the whole of what a visitor needs to know.
  const modelNote =
    meta?.providers?.find((p) => !p.available && p.note)?.note ?? "";

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
          {(meta?.providers?.length ?? 0) > 0 && (
            <div className="models" role="group" aria-label="Model">
              {meta!.providers.map((choice) => (
                <button
                  key={choice.name}
                  type="button"
                  className={`model ${provider === choice.name ? "on" : ""}`}
                  onClick={() => setProvider(choice.name)}
                  disabled={!choice.available}
                  title={
                    choice.available
                      ? `${choice.label} — ${choice.model}`
                      : `${choice.label} unavailable: ${choice.note}`
                  }
                >
                  {choice.label}
                </button>
              ))}
            </div>
          )}
          <span className="hint">
            ⌘/Ctrl + Enter
            {activeModel && ` · ${activeModel}`}
          </span>
        </div>
        {modelNote && <p className="model-note">{modelNote}</p>}
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

          {result.citations.length > 0 && (() => {
            const sections = groupBySection(result.citations);
            const excerpts = sections.reduce((n, s) => n + s.quotes.length, 0);
            return (
            <section className="panel">
              <h2>
                Citations — {sections.length}{" "}
                {sections.length === 1 ? "section" : "sections"}, {excerpts}{" "}
                {excerpts === 1 ? "excerpt" : "excerpts"} verified against the
                source
                {showTranslation && " · quoted text stays in English"}
              </h2>
              {sections.map((citation) => (
                <article className="cite" key={citation.key}>
                  <div className="cite-head">
                    <span className="cite-num">
                      {citation.source === "ScheduleII"
                        ? `Schedule II · Penal Code s.${citation.section}`
                        : `Section ${citation.section}`}
                    </span>
                    <span className="cite-note">{citation.marginal_note}</span>
                    <span
                      className={`badge ${citation.verified > 0 ? "ok" : "no"}`}
                    >
                      {citation.verified === 0
                        ? "no verified quote"
                        : citation.verified === 1
                          ? "quote verified"
                          : `${citation.verified} quotes verified`}
                    </span>
                  </div>
                  {(citation.part || citation.chapter) && (
                    <div className="cite-path">
                      {[citation.part, citation.chapter]
                        .filter(Boolean)
                        .join(" › ")}
                    </div>
                  )}
                  {citation.offence && (
                    <>
                      <p className="offence-lede">
                        The row itself, from the parsed table — not model output
                      </p>
                      <dl className="offence">
                        <div>
                          <dt>Cognizable</dt>
                          <dd>
                            {OFFENCE_VALUE[citation.offence.cognizable] ??
                              citation.offence.cognizable}
                          </dd>
                        </div>
                        <div>
                          <dt>Bailable</dt>
                          <dd>
                            {OFFENCE_VALUE[citation.offence.bailable] ??
                              citation.offence.bailable}
                          </dd>
                        </div>
                        <div>
                          <dt>Compoundable</dt>
                          <dd>
                            {OFFENCE_VALUE[citation.offence.compoundable] ??
                              citation.offence.compoundable}
                          </dd>
                        </div>
                        {citation.offence.punishment && (
                          <div>
                            <dt>Punishment</dt>
                            <dd>{citation.offence.punishment}</dd>
                          </div>
                        )}
                        {citation.offence.triable_by && (
                          <div>
                            <dt>Triable by</dt>
                            <dd>{citation.offence.triable_by}</dd>
                          </div>
                        )}
                        {citation.offence.warrant_or_summons && (
                          <div>
                            <dt>First process</dt>
                            <dd>{citation.offence.warrant_or_summons}</dd>
                          </div>
                        )}
                      </dl>
                    </>
                  )}
                  {citation.quotes.map((quote) => (
                    <blockquote key={quote}>{quote}</blockquote>
                  ))}
                  {citation.amendments?.length > 0 && (
                    <details className="amend">
                      <summary>
                        {amendmentSummary(citation.amendments)}
                      </summary>
                      <ul>
                        {citation.amendments.map((a, i) => (
                          <li key={`${a.operation}-${a.effective_from}-${i}`}>
                            <span className={`op ${a.operation}`}>
                              {a.operation}
                            </span>
                            <span className="when">
                              {a.effective_from
                                ? formatDate(a.effective_from)
                                : "date not stated"}
                            </span>
                            <p>{a.text}</p>
                            {a.source_url && (
                              <a
                                href={a.source_url}
                                target="_blank"
                                rel="noopener noreferrer"
                              >
                                {a.amending_act_title ??
                                  `Act ${a.act_number ?? ""}`.trim()}{" "}
                                →
                              </a>
                            )}
                          </li>
                        ))}
                      </ul>
                    </details>
                  )}
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
            );
          })()}

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
