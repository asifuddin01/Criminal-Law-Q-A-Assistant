/**
 * Record a short demo by driving the real application.
 *
 *   node scripts/record-demo.mjs [output-basename]
 *   MODEL=local node scripts/record-demo.mjs demo-local-model
 *
 * Both servers must be running. Which model answers is chosen in the page, so
 * MODEL picks it here rather than the recording depending on how the backend
 * happened to be started; unset, it records whatever the deployment defaults to.
 * Generated rather than screen-captured, for the same reason the screenshots
 * are: a recording nobody can reproduce is a claim about a version of the app
 * that no longer exists.
 *
 * Three questions, chosen because each shows a different thing the system does:
 * a section with amendment history, an offence answered from Schedule II rather
 * than by retrieval, and a question the corpus cannot answer — refusal being a
 * feature here, not a failure.
 */
import { chromium } from "playwright";
import { mkdir, rename, readdir, rm, stat } from "node:fs/promises";
import { rmSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, "..", "..", "docs");
const RAW = join(OUT, ".video-raw");
const APP = process.env.APP_URL ?? "http://localhost:3000";
// The local model answers in tens of seconds on CPU, the hosted one in a few.
const ANSWER_TIMEOUT = Number(process.env.ANSWER_TIMEOUT ?? 180_000);
const BASENAME = process.argv[2] ?? "demo";
// "hosted" | "local" | unset. The label on the button, which is also what a
// viewer of the recording sees selected.
const MODEL = process.env.MODEL ?? "";

const QUESTIONS = [
  {
    text: "When may a police officer arrest a person without a warrant?",
    shows: "section 54, with the amendment that produced its current wording",
  },
  {
    text: "Is theft a bailable offence?",
    shows: "answered from the Schedule II row, not from the sections about bail",
  },
  {
    text: "What is the punishment for insider trading under Bangladeshi law?",
    shows: "outside the corpus — the system declines instead of inventing",
  },
];

async function ask(page, question) {
  const box = page.locator("textarea").first();
  await box.click();
  await box.fill("");
  // Typed rather than filled, so the recording reads as someone using it.
  await box.type(question, { delay: 18 });
  await page.waitForTimeout(400);
  await page.getByRole("button", { name: "Ask", exact: true }).click();

  const answered = page.locator("section.panel").first();
  const failed = page.locator("div.error").first();
  await Promise.race([
    answered.waitFor({ timeout: ANSWER_TIMEOUT }),
    failed.waitFor({ timeout: ANSWER_TIMEOUT }),
  ]);
  if (await failed.isVisible().catch(() => false)) {
    throw new Error(`API error: ${(await failed.innerText()).slice(0, 200)}`);
  }
  // Long enough to read the answer and its citations.
  await page.waitForTimeout(2600);
  await page.mouse.wheel(0, 650);
  await page.waitForTimeout(2200);
  await page.mouse.wheel(0, -650);
  await page.waitForTimeout(700);
}

await rm(RAW, { recursive: true, force: true });
await mkdir(OUT, { recursive: true });

// A failed recording must not leave its scratch directory behind: the first
// hosted attempt errored on a spent quota and the raw frames were committed.
process.on("exit", () => {
  try {
    rmSync(RAW, { recursive: true, force: true });
  } catch {}
});

const browser = await chromium.launch({ channel: "chrome" });
const context = await browser.newContext({
  viewport: { width: 1280, height: 860 },
  recordVideo: { dir: RAW, size: { width: 1280, height: 860 } },
  colorScheme: "dark",
});
const page = await context.newPage();

await page.goto(APP, { waitUntil: "networkidle" });
await page.waitForTimeout(1800);

if (MODEL) {
  // The control only exists once /api/meta has said which models this
  // deployment has, so it is waited for rather than assumed.
  const label = MODEL === "local" ? "Local" : "Hosted";
  const button = page.locator(".models button", { hasText: label }).first();
  await button.waitFor({ timeout: 15_000 });
  if (await button.isDisabled()) {
    throw new Error(`the ${label} model is not available in this deployment`);
  }
  await button.click();
  await page.waitForTimeout(900);
}

for (const { text, shows } of QUESTIONS) {
  console.log(`  asking: ${text}`);
  console.log(`     shows: ${shows}`);
  await ask(page, text);
}

await page.waitForTimeout(800);
await context.close();
await browser.close();

const [file] = (await readdir(RAW)).filter((n) => n.endsWith(".webm"));
if (!file) throw new Error("playwright wrote no video");
const destination = join(OUT, `${BASENAME}.webm`);
await rename(join(RAW, file), destination);
await rm(RAW, { recursive: true, force: true });
const { size } = await stat(destination);
console.log(`\nwrote docs/${BASENAME}.webm (${(size / 1e6).toFixed(1)} MB)`);
