// Render the state-AGs map from a built modelmirror.ai site as PNGs.
//
//   node render-map.mjs <site-dist> <out-dir>
//
// The site draws the map (the page's only figure) from board.json; this
// serves the built site locally, opens /state-ags/ and screenshots the map
// with its legend once per highlight: every office, then each lens the page
// offers. The section's heading goes above each image and a line under it
// names the page and the board's day, so a copy shared on its own still says
// what it shows and when. The images are
// copies of the page, never a second drawing of the data.
import { createServer } from "node:http";
import { readFile, mkdir } from "node:fs/promises";
import { extname, join, normalize, resolve } from "node:path";
import { chromium } from "playwright";

const [dist, out] = process.argv.slice(2).map((p) => p && resolve(p));
if (!dist || !out) {
  console.error("usage: node render-map.mjs <site-dist> <out-dir>");
  process.exit(2);
}

// Each view: the radio the page's CSS reads, and the file it is written to.
const VIEWS = [
  { lens: "none", file: "map.png" },
  { lens: "led", file: "map-led.png" },
  { lens: "leverage", file: "map-leverage.png" },
  { lens: "turnover", file: "map-turnover.png" },
];

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css",
  ".js": "text/javascript",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
  ".woff": "font/woff",
  ".json": "application/json",
  ".webmanifest": "application/manifest+json",
};

const server = createServer(async (req, res) => {
  const path = normalize(decodeURIComponent(new URL(req.url, "http://x").pathname));
  let file = join(dist, path);
  if (!file.startsWith(dist)) {
    res.writeHead(403).end();
    return;
  }
  if (path.endsWith("/")) file = join(file, "index.html");
  try {
    const body = await readFile(file);
    res.writeHead(200, { "content-type": TYPES[extname(file)] ?? "application/octet-stream" }).end(body);
  } catch {
    res.writeHead(404).end();
  }
});
await new Promise((ok) => server.listen(0, "127.0.0.1", ok));
const base = `http://127.0.0.1:${server.address().port}`;

await mkdir(out, { recursive: true });
const browser = await chromium.launch();
try {
  const page = await browser.newPage({
    viewport: { width: 960, height: 1400 },
    deviceScaleFactor: 2,
    colorScheme: "light",
  });
  for (const view of VIEWS) {
    const response = await page.goto(`${base}/state-ags/`, { waitUntil: "networkidle" });
    if (!response?.ok()) throw new Error(`/state-ags/ answered ${response?.status()}`);
    await page.evaluate(() => document.fonts.ready);
    const radio = page.locator(`#lens-${view.lens}`);
    if ((await radio.count()) !== 1) throw new Error(`the page has no #lens-${view.lens} highlight`);
    await radio.check();
    const figure = page.locator("figure.ag-map");
    if ((await figure.count()) !== 1) throw new Error("the page has no figure.ag-map");
    await figure.evaluate((fig) => {
      const stamp = document.querySelector(".stamp");
      const day = stamp?.textContent?.match(/Read on ([A-Z][a-z]{2} \d{1,2}, \d{4})/)?.[1];
      if (!day) throw new Error("the page states no board day");
      const heading = document.querySelector("#map-h")?.textContent?.trim();
      if (!heading) throw new Error("the page has no map heading");
      const title = document.createElement("p");
      title.textContent = heading;
      title.style.cssText = "margin:0 0 0.75rem;font-size:1.25rem;font-weight:700";
      fig.prepend(title);
      fig.style.padding = "1rem";
      const line = document.createElement("p");
      line.textContent = `State attorneys general and AI · modelmirror.ai/state-ags · read on ${day}`;
      line.style.cssText = "margin:0.75rem 0 0;font-size:0.8rem;opacity:0.75";
      fig.append(line);
    });
    await figure.screenshot({ path: join(out, view.file), animations: "disabled" });
    console.log(`wrote ${view.file}`);
  }
} finally {
  await browser.close();
  server.close();
}
