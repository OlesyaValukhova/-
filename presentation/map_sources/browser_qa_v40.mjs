import { chromium } from "playwright";
import fs from "node:fs/promises";
import path from "node:path";
import http from "node:http";

const root = process.cwd();
const htmlPath = path.join(root, "presentation", "age_accessibility_b1_v40.html");
const outputDir = path.join(root, "presentation", "browser_qa_v40");
await fs.mkdir(outputDir, { recursive: true });
const speechPath = path.join(root, "presentation", "speaker_script_v12.md");
const speechText = await fs.readFile(speechPath, "utf8");
const speechLines = speechText.split(/\r?\n/).filter(line => /^\d+\.\s/.test(line));
const speechWordCounts = speechLines.map(line => line.trim().split(/\s+/).length);
const speechOverLimit = speechWordCounts
  .map((words, index) => ({ slide: index + 1, words }))
  .filter(item => item.words > 45);

const mime = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
};

const server = http.createServer(async (req, res) => {
  try {
    const pathname = decodeURIComponent(new URL(req.url, "http://127.0.0.1").pathname);
    const file = path.resolve(root, "." + pathname);
    if (file !== root && !file.startsWith(root + path.sep)) {
      res.writeHead(403).end("Forbidden");
      return;
    }
    const data = await fs.readFile(file);
    res.writeHead(200, { "Content-Type": mime[path.extname(file)] || "application/octet-stream" });
    res.end(data);
  } catch {
    res.writeHead(404).end("Not found");
  }
});

await new Promise(resolve => server.listen(4173, "127.0.0.1", resolve));
const browser = await chromium.launch({ headless: true });
const failures = [];
const consoleErrors = [];
const pageErrors = [];
const slides = [];
let documentImages = [];

try {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
  });
  page.on("pageerror", error => pageErrors.push(error.message));
  page.on("console", message => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  await page.goto("http://127.0.0.1:4173/presentation/age_accessibility_b1_v40.html", {
    waitUntil: "networkidle",
  });
  await page.locator("img").evaluateAll(async images => {
    await Promise.all(images.map(img => img.decode().catch(() => null)));
  });
  const initialCount = (await page.locator("#count").textContent())?.trim();
  if (initialCount !== "1 / 20") failures.push("Deck did not initialize at slide 1 of 20");
  await page.locator("#toggle").click();

  for (let n = 1; n <= 20; n++) {
    if (n > 1) await page.locator("#next").click();
    const expected = `${n} / 20`;
    await page.waitForFunction(value => document.querySelector("#count")?.textContent?.trim() === value, expected);
    await page.locator("#body img").evaluateAll(async images => {
      await Promise.all(images.map(img => img.decode().catch(() => null)));
    });

    const state = await page.evaluate(() => {
      const frame = document.querySelector(".frame");
      const body = document.querySelector("#body");
      const title = document.querySelector("#title");
      const note = document.querySelector("#note");
      const inner = document.querySelector(".inner");
      const frameRect = frame.getBoundingClientRect();
      const overflow = [];
      for (const el of body.querySelectorAll("*")) {
        const style = getComputedStyle(el);
        if (style.display === "none" || style.visibility === "hidden") continue;
        const r = el.getBoundingClientRect();
        if (!r.width || !r.height) continue;
        if (r.left < frameRect.left - 2 || r.right > frameRect.right + 2 ||
            r.top < frameRect.top - 2 || r.bottom > frameRect.bottom + 2) {
          overflow.push({
            tag: el.tagName.toLowerCase(),
            className: String(el.className || ""),
            left: Math.round(r.left - frameRect.left),
            right: Math.round(r.right - frameRect.right),
            top: Math.round(r.top - frameRect.top),
            bottom: Math.round(r.bottom - frameRect.bottom),
          });
        }
      }
      const images = [...body.querySelectorAll("img")].map(img => ({
        src: img.getAttribute("src"),
        loaded: img.complete && img.naturalWidth > 0,
        alt: (img.getAttribute("alt") || "").trim(),
        width: img.naturalWidth,
        height: img.naturalHeight,
      }));
      return {
        title: title.textContent.trim(),
        note: note.textContent.trim(),
        frameBackground: getComputedStyle(frame).backgroundColor,
        headingFontSize: getComputedStyle(title).fontSize,
        bodyScrollHeight: body.scrollHeight,
        bodyClientHeight: body.clientHeight,
        innerScrollWidth: inner.scrollWidth,
        innerClientWidth: inner.clientWidth,
        viewportScrollWidth: document.documentElement.scrollWidth,
        viewportWidth: window.innerWidth,
        overflow,
        images,
      };
    });

    const slideFailures = [];
    const expectedMapAssets = {
      12: "assets_v40/programming_states_b1.png",
      13: "assets_v40/art_states_b1.png",
      15: "assets_v40/paired_delta_programming_art_b1_preview.png",
      19: "assets_v40/network_coverage_b1.png",
    };
    if (expectedMapAssets[n] && !state.images.some(image => image.src === expectedMapAssets[n])) {
      slideFailures.push(`expected map asset not used: ${expectedMapAssets[n]}`);
    }
    if (!state.title) slideFailures.push("empty title");
    if (state.note.length < 20) slideFailures.push("missing/short speaker note");
    if (state.frameBackground !== "rgb(255, 255, 255)") slideFailures.push("frame background is not white");
    if (state.viewportScrollWidth > state.viewportWidth + 2) slideFailures.push("horizontal viewport overflow");
    if (state.innerScrollWidth > state.innerClientWidth + 3) slideFailures.push("horizontal inner overflow");
    if (state.overflow.length) slideFailures.push("content extends beyond slide frame");
    for (const image of state.images) {
      if (!image.loaded) slideFailures.push(`image failed to load: ${image.src}`);
      if (!image.alt) slideFailures.push(`image has no alt text: ${image.src}`);
    }

    await page.locator(".frame").screenshot({
      path: path.join(outputDir, `slide-${String(n).padStart(2, "0")}.png`),
      animations: "disabled",
    });

    slides.push({
      slide: n,
      title: state.title,
      note_chars: state.note.length,
      frame_background: state.frameBackground,
      heading_font_size: state.headingFontSize,
      body_scroll: state.bodyScrollHeight - state.bodyClientHeight,
      inner_horizontal_overflow: state.innerScrollWidth - state.innerClientWidth,
      viewport_horizontal_overflow: state.viewportScrollWidth - state.viewportWidth,
      image_count: state.images.length,
      images: state.images,
      overflow_elements: state.overflow,
      status: slideFailures.length ? "failed" : "passed",
      failures: slideFailures,
    });
    for (const failure of slideFailures) failures.push(`Slide ${n}: ${failure}`);
  }

  documentImages = await page.locator("img").evaluateAll(images => images.map(img => ({
    src: img.getAttribute("src"),
    loaded: img.complete && img.naturalWidth > 0,
    alt: (img.getAttribute("alt") || "").trim(),
    width: img.naturalWidth,
    height: img.naturalHeight,
  })));
  for (const image of documentImages) {
    if (!image.loaded) failures.push(`document image failed to load: ${image.src}`);
    if (!image.alt) failures.push(`document image has no alt text: ${image.src}`);
  }
  const lastCount = (await page.locator("#count").textContent())?.trim();
  if (lastCount !== "20 / 20") failures.push("Deck did not reach slide 20");
  if (await page.locator("#next").isEnabled()) failures.push("Next button remains enabled on final slide");
} finally {
  await browser.close();
  await new Promise(resolve => server.close(resolve));
}

if (speechLines.length !== 20) failures.push(`Expected 20 numbered speech lines, got ${speechLines.length}`);
if (speechOverLimit.length) failures.push(`Speech lines exceed 45-word soft limit: ${JSON.stringify(speechOverLimit)}`);

const report = {
  version: "v40",
  viewport: "1440x900",
  slide_count: slides.length,
  rendered_slide_count: slides.filter(s => s.status === "passed").length,
  speech_line_count: speechLines.length,
  speech_max_words: Math.max(0, ...speechWordCounts),
  speech_over_45_words: speechOverLimit,
  document_images: documentImages,
  page_errors: pageErrors,
  console_errors: consoleErrors,
  failures,
  slides,
};
await fs.writeFile(path.join(outputDir, "report.json"), JSON.stringify(report, null, 2) + "\n", "utf8");
console.log(JSON.stringify({
  version: report.version,
  slide_count: report.slide_count,
  passed: report.rendered_slide_count,
  speech_line_count: report.speech_line_count,
  speech_max_words: report.speech_max_words,
  failures: report.failures,
  page_errors: report.page_errors,
  console_errors: report.console_errors,
}, null, 2));

if (failures.length || pageErrors.length || consoleErrors.length) process.exitCode = 1;
