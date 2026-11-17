import { chromium } from "playwright";
import fs from "node:fs/promises";
import path from "node:path";
import http from "node:http";

const root = process.cwd();
const htmlPath = path.join(root, "presentation", "age_accessibility_b1_v45.html");
const outputDir = path.join(root, "presentation", "browser_qa_v45");
await fs.mkdir(outputDir, { recursive: true });
const speechPath = path.join(root, "presentation", "speaker_script_v16.md");
const speechText = await fs.readFile(speechPath, "utf8");
const locatorSvgPath = path.join(root, "presentation", "assets_v44", "district_locator_v44.svg");
const locatorAuditPath = path.join(root, "presentation", "map_sources", "district_locator_audit_v44.json");
const locatorSvgText = await fs.readFile(locatorSvgPath, "utf8");
const locatorAudit = JSON.parse(await fs.readFile(locatorAuditPath, "utf8"));
const markerPattern = new RegExp('<circle cx="([0-9.]+)" cy="([0-9.]+)" r="14"[^>]*/><text[^>]*>([0-9]+)</text>', "g");
const locatorMarkers = [...locatorSvgText.matchAll(markerPattern)]
  .map(match => ({ x: Number(match[1]), y: Number(match[2]), number: Number(match[3]) }));
const locatorDistances = locatorMarkers.flatMap((a, i) =>
  locatorMarkers.slice(i + 1).map(b => Math.hypot(a.x - b.x, a.y - b.y))
);
const locatorMinSpacing = locatorDistances.length ? Math.min(...locatorDistances) : 0;
const locatorHasAttribution = locatorSvgText.includes("© OpenStreetMap contributors") && locatorSvgText.includes("ODbL 1.0");
const locatorAuditNumbers = locatorAudit.districts.map(district => district.number);
const locatorAuditOsmIdsUnique = new Set(locatorAudit.districts.map(district => district.osm_id)).size === 18;
const locatorAuditPositionsMatch = locatorAudit.districts.every(district => {
  const marker = locatorMarkers.find(item => item.number === district.number);
  return marker && Math.abs(marker.x - district.label_position_svg_px[0]) < 0.05 &&
    Math.abs(marker.y - district.label_position_svg_px[1]) < 0.05;
});
const speechLines = speechText.split(/\r?\n/).filter(line => /^\d+\.\s/.test(line));
const speechWordCounts = speechLines.map(line => line.trim().split(/\s+/).length);
const speechOverLimit = speechWordCounts
  .map((words, index) => ({ slide: index + 1, words }))
  .filter(item => item.words > 45);
const speechHeader = speechText.split("\n").find(line => line.startsWith("# "));
const speechVersion = speechHeader?.match(/v([0-9]+)/)?.[1] || null;
const speechSlideNumbers = speechLines.map(line => Number(line.match(/^([0-9]+)\./)?.[1] || 0));

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
if (locatorMarkers.length !== 18) failures.push(`Locator SVG must contain 18 numbered district markers, got ${locatorMarkers.length}`);
if (locatorAudit.version !== "v44" || locatorAudit.label_count !== 18 || locatorAudit.districts.length !== 18) failures.push("Locator JSON audit must describe 18 districts in v44");
if (JSON.stringify(locatorAuditNumbers) !== JSON.stringify(Array.from({length: 18}, (_, i) => i + 1))) failures.push("Locator audit numbers must be sequential 1–18");
if (!locatorAuditOsmIdsUnique) failures.push("Locator audit OSM relation IDs must be unique");
if (!locatorAuditPositionsMatch) failures.push("Locator audit marker positions do not match SVG");
if (Math.abs(locatorAudit.minimum_marker_spacing_px - locatorMinSpacing) > 0.05) failures.push("Locator audit marker spacing does not match SVG");
if (locatorSvgText.includes("NaN")) failures.push("Locator SVG contains invalid NaN coordinates");
if (!locatorHasAttribution) failures.push("Locator SVG is missing OpenStreetMap / ODbL attribution");
if (locatorMinSpacing < 30) failures.push(`Locator district markers overlap: minimum spacing ${locatorMinSpacing}`);
if (speechVersion !== "16") failures.push(`Expected speaker_script_v16.md header, got: ${speechHeader || "missing"}`);
if (JSON.stringify(speechSlideNumbers) !== JSON.stringify(Array.from({length: 20}, (_, i) => i + 1))) {
  failures.push(`Speaker script numbering must be exactly 1–20, got: ${JSON.stringify(speechSlideNumbers)}`);
}
const consoleErrors = [];
const pageErrors = [];
const slides = [];
let documentTitle = "";
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

  await page.goto("http://127.0.0.1:4173/presentation/age_accessibility_b1_v45.html", {
    waitUntil: "networkidle",
  });
  documentTitle = await page.title();
  if (!documentTitle.includes("v45")) failures.push("Document title is not v45");
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
        bodyText: body.innerText.trim(),
        detail: document.querySelector("#note-detail")?.textContent.trim() || "",
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
        districtListCount: document.querySelectorAll(".district-item").length,
        districtNumbers: [...document.querySelectorAll(".district-num")].map(el => Number(el.textContent.trim())),
        districtNames: [...document.querySelectorAll(".district-item")].map(el => el.querySelectorAll("span")[1]?.textContent.trim() || ""),
      };
    });

    const slideFailures = [];
    const expectedMapAssets = {
      10: "assets_v44/district_locator_v44.svg",
      12: "assets_v42/programming_states_b1.png",
      13: "assets_v42/art_states_b1.png",
      15: "assets_v42/paired_delta_programming_art_b1_preview.png",
      19: "assets_v42/network_coverage_b1.png",
    };
    if (expectedMapAssets[n] && !state.images.some(image => image.src === expectedMapAssets[n])) {
      slideFailures.push(`expected map asset not used: ${expectedMapAssets[n]}`);
    }
    if (n === 10) {
      if (state.districtListCount !== 18) slideFailures.push(`district locator must list 18 districts, got ${state.districtListCount}`);
      if (JSON.stringify(state.districtNumbers) !== JSON.stringify(Array.from({length: 18}, (_, i) => i + 1))) slideFailures.push("district locator numbers must be sequential 1–18");
      if (JSON.stringify(state.districtNames) !== JSON.stringify(locatorAudit.districts.map(district => district.name))) slideFailures.push("district locator list does not match the OSM audit index");
      if (!state.note.includes("районов") || !state.note.includes("BlocksNet")) slideFailures.push("slide 10 note must distinguish district context from BlocksNet analysis");
      if (!state.bodyText.includes("OpenStreetMap") || !state.bodyText.includes("ODbL 1.0")) slideFailures.push("district locator attribution is missing");
      if (!state.images.some(image => image.alt.includes("18 административных районов"))) slideFailures.push("district locator alt text is missing");
    }
    if ([12, 13, 15, 19].includes(n)) {
      if (!state.note.includes("OpenStreetMap") || !state.note.includes("BlocksNet")) {
        slideFailures.push("district boundaries are not identified as contextual OSM data");
      }
      if (!state.images.some(image => image.alt.includes("административные границы районов"))) {
        slideFailures.push("map alt text does not identify the OSM district-boundary overlay");
      }
    }
    if (n === 3) {
      if (!state.bodyText.includes("перечень добровольного применения") || !state.bodyText.includes("обязательность этих пунктов отдельно не подтверждена")) slideFailures.push("missing SP 460 scope / voluntary-list caveat");
      if (!state.bodyText.includes("обязательность этих пунктов отдельно не подтверждена")) slideFailures.push("missing legal-status qualification");
      if (!state.bodyText.includes("однопрофильные общеразвивающие")) slideFailures.push("microdistrict program type is underspecified");
      if (!state.bodyText.includes("транспортом")) slideFailures.push("district transport-access wording is missing");
      if (!state.note.includes("B1 использует отдельный порог")) slideFailures.push("speaker note does not distinguish B1 from 750 m");
      if (!state.detail.includes("реестр требований") || !state.detail.includes("обязательность именно этих пунктов отдельно не подтверждена")) slideFailures.push("extended note omits registry-status caveat");
    }
    if (n === 1) {
      if (!state.bodyText.includes("доступность опубликованных площадок с карточками")) slideFailures.push("slide 1 must define the research object as published venue coordinates with age-eligible cards");
      if (!state.bodyText.includes("пространственных предпосылках сопровождения")) slideFailures.push("slide 1 must frame accompaniment as a spatial precondition, not a measured outcome");
    }
    if (n === 17) {
      if (!state.bodyText.includes("В МОДЕЛИ B1") || !state.bodyText.includes("НЕ ИЗМЕРЯЕТСЯ")) slideFailures.push("slide 17 must distinguish what B1 measures from what it does not measure");
      if (!state.bodyText.includes("Сопровождение — возможный сценарий, не результат модели")) slideFailures.push("slide 17 must not present accompaniment as a model result");
      if (!state.note.includes("не подтверждает") || !state.note.includes("не измеряются")) slideFailures.push("slide 17 note must state catalogue and family-behaviour limitations");
      if (!state.detail.includes("N — число уникальных опубликованных координат") || !state.detail.includes("свободных мест")) slideFailures.push("slide 17 extended note must define N and its limits");
    }
    if (n === 18) {
      if (!state.bodyText.includes("АДРЕС") || !state.bodyText.includes("В КАТАЛОГЕ")) slideFailures.push("slide 18 destination must be identified as a catalogue address, not a confirmed active class");
      if (!state.note.includes("не подтверждает") || !state.note.includes("расписание школы")) slideFailures.push("slide 18 note must state that activity and schedule are not confirmed by B1");
    }
    if (n === 20) {
      if (!state.bodyText.includes("Площадка.") || !state.bodyText.includes("проверить маршрут и расписание")) slideFailures.push("slide 20 must close with the actual measured object and next research step");
      if (!state.note.includes("эти данные в B1 не измерялись")) slideFailures.push("slide 20 note must preserve the evidence boundary");
    }
    if (!state.title) slideFailures.push("empty title");
    if (state.note.length < 20) slideFailures.push("missing/short speaker note");
    if (state.frameBackground !== "rgb(255, 255, 255)") slideFailures.push("frame background is not white");
    if (state.bodyScrollHeight > state.bodyClientHeight + 3) slideFailures.push("vertical body overflow");
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
      district_list_count: state.districtListCount,
      district_numbers: state.districtNumbers,
      district_names: state.districtNames,
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
  version: "v45",
  document_title: documentTitle,
  viewport: "1440x900",
  slide_count: slides.length,
  rendered_slide_count: slides.filter(s => s.status === "passed").length,
  speaker_script_file: "presentation/speaker_script_v16.md",
  speaker_script_heading: speechHeader,
  speaker_script_version: speechVersion,
  speaker_script_sha256: (await import("node:crypto")).createHash("sha256").update(speechText).digest("hex"),
  locator_map_marker_count: locatorMarkers.length,
  locator_map_minimum_marker_spacing_px: Number(locatorMinSpacing.toFixed(2)),
  locator_map_has_osm_attribution: locatorHasAttribution,
  locator_map_audit_file: "presentation/map_sources/district_locator_audit_v44.json",
  locator_map_audit_district_count: locatorAudit.districts.length,
  locator_map_audit_osm_ids_unique: locatorAuditOsmIdsUnique,
  locator_map_audit_positions_match: locatorAuditPositionsMatch,
  speech_slide_numbers: speechSlideNumbers,
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
