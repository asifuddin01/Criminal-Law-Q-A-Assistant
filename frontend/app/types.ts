export interface Citation {
  section: string;
  source: string;
  marginal_note: string;
  part: string | null;
  chapter: string | null;
  quote: string;
  quote_verified: boolean;
  source_url: string;
}

export interface DroppedCitation {
  section: string;
  source: string;
  reason: string;
  quote: string | null;
}

export interface AskResponse {
  question_text: string;
  answer: string;
  refused: boolean;
  reason: string;
  citations: Citation[];
  dropped_citations: DroppedCitation[];
  retrieved_sections: string[];
  model: string;
  disclaimer: string;
}

export interface Meta {
  app_name: string;
  version: string;
  provider: {
    name: string;
    chat_model: string;
    capabilities: string[];
    reachable: boolean | null;
  };
  disclaimer: string;
  source_attribution: string;
}

export interface Translation {
  text: string;
  target: string;
  model: string;
  notice: string;
}

export interface Transcription {
  text: string;
  language: string | null;
  model: string;
  seconds: number;
}

export interface UploadedDocument {
  document_id: string;
  filename: string;
  pages: number;
  characters: number;
  preview: string;
  notice: string;
}

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8010";
