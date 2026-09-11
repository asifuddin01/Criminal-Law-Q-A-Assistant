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

const browser = await chromium.launch({ channel: "chrome" });
await mkdir(OUT, { recursive: true });

for (const shot of SHOTS) {
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
