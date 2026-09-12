/**
 * Capture the README screenshots by driving the real application.
 *
 *   node scripts/capture-screenshots.mjs
 *
 * Both servers must be running. Uses the installed Chrome rather than downloading
 * a browser.
 *
 * Screenshots are generated rather than pasted so they can be regenerated when the
 * interface changes. A screenshot nobody can reproduce becomes a claim about a
 * version of the app that no longer exists.
 */
import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, "..", "..", "docs", "screenshots");
const APP = process.env.APP_URL ?? "http://localhost:3000";
const ANSWER_TIMEOUT = 90_000;

const SHOTS = [
  {
    name: "01-landing",
    caption: "Landing state, with the legal-information disclaimer up front",
    async run() {},
  },
  {
    name: "02-answer-verified-citations",
    caption: "An English answer with citations verified against the source",
    async run(page) {
      await askExample(page, "How long can police detain");
    },
  },
  {
    name: "03-bangla-question-english-answer",
    caption: "A Bangla question answered from the English corpus",
    async run(page) {
      await askExample(page, "পুলিশ কখন");
    },
  },
  {
    name: "04-translated-to-bangla",
    caption:
      "The same answer translated on demand — statutory excerpts stay in English",
    async run(page) {
      await askExample(page, "পুলিশ কখন");
      await page.getByRole("button", { name: "বাংলায় দেখুন" }).click();
      await page.getByRole("button", { name: "Show in English" }).waitFor({
        timeout: ANSWER_TIMEOUT,
      });
      await page.waitForTimeout(400);
    },
  },
  {
    name: "05-amendment-provenance",
    caption:
      "Every citation carries how and when the section changed, and under which act",
    async run(page) {
      await askExample(page, "When may a police officer arrest");
      // Section 54 was substituted with effect from 10 August 2025, which is the
      // point of the shot: the current wording alone does not tell a reader that,
      // and whether it governs a matter depends on when the matter arose.
      const histories = page.locator("details.amend > summary");
      const count = await histories.count();
      for (let i = 0; i < count; i += 1) {
        await histories.nth(i).click();
      }
      await page.waitForTimeout(400);
    },
  },
  {
    name: "06-schedule-ii-row",
    caption: "A Schedule II citation carries the parsed row, not only the quoted line",
    async run(page) {
      // The shot exists because of what it replaced: asked this, the local model
      // quoted the row's cognizability line — verbatim, verified, and about a
      // different column. The row is parsed, so it is shown rather than chosen.
      await askExample(page, "Is theft a bailable offence");
    },
  },
];

async function askExample(page, fragment) {
  const button = page.locator("button", { hasText: fragment }).first();
  await button.click();

  // Wait for whichever comes first: an answer, or the error the page already
  // renders. Waiting only for success turns a visible API failure into a silent
  // two-minute timeout that says nothing about what went wrong.
  const answer = page.locator("section.panel").first();
  const failure = page.locator("div.error").first();
  await Promise.race([
    answer.waitFor({ timeout: ANSWER_TIMEOUT }),
    failure.waitFor({ timeout: ANSWER_TIMEOUT }),
  ]);

  if (await failure.isVisible().catch(() => false)) {
    throw new Error(`API error: ${(await failure.innerText()).slice(0, 160)}`);
  }
  await page.waitForTimeout(400);
}

// Capture a subset by name fragment: `node scripts/capture-screenshots.mjs 04`.
// A full run costs several model calls against a small daily allowance, so being
// able to redo only the shot that failed matters more than it sounds.
const only = process.argv.slice(2);
const selected = only.length
  ? SHOTS.filter((s) => only.some((fragment) => s.name.includes(fragment)))
  : SHOTS;

if (!selected.length) {
  console.error(`no shots match ${only.join(", ")}`);
  process.exit(1);
}

const browser = await chromium.launch({ channel: "chrome" });
await mkdir(OUT, { recursive: true });

for (const shot of selected) {
  const context = await browser.newContext({
    viewport: { width: 1000, height: 1400 },
    deviceScaleFactor: 2,
    colorScheme: process.env.THEME === "light" ? "light" : "dark",
  });
  const page = await context.newPage();
  await page.goto(APP, { waitUntil: "networkidle" });

  try {
    await shot.run(page);
    const path = join(OUT, `${shot.name}.png`);
    await page.screenshot({ path, fullPage: true });
    console.log(`✓ ${shot.name}  ${shot.caption}`);
  } catch (error) {
    console.error(`✗ ${shot.name}: ${error.message.split("\n")[0]}`);
  } finally {
    await context.close();
  }
}

await browser.close();
console.log(`\nwritten to docs/screenshots/`);
