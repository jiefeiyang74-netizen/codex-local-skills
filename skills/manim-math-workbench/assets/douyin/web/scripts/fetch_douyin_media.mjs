import fs from "node:fs";
import process from "node:process";
import { chromium } from "playwright-core";

const videoId = String(process.argv[2] || "").trim();
if (!/^\d{10,}$/.test(videoId)) {
  process.stderr.write("A numeric Douyin video ID is required.\n");
  process.exit(1);
}

const executablePath = findBrowser();
if (!executablePath) {
  process.stderr.write("Chrome or Edge was not found for the Douyin browser fallback.\n");
  process.exit(1);
}

const timeoutMs = Number(process.env.DYT_BROWSER_TIMEOUT_MS || 90000);
const maxAttempts = Number(process.env.DYT_BROWSER_ATTEMPTS || 2);
let lastError;
let output;

for (let attempt = 1; attempt <= maxAttempts; attempt++) {
  try {
    const detail = await lookupVideoDetail(executablePath, videoId, timeoutMs);
  const video = detail.video || {};
  const audioEntries = Array.isArray(video.bit_rate_audio)
    ? video.bit_rate_audio
    : (video.bit_rate_audio ? [video.bit_rate_audio] : []);
  const audioURLs = uniqueURLs([
    ...audioEntries.flatMap(item => [
      item?.url_list?.main_url,
      item?.url_list?.backup_url,
      item?.url_list?.fallback_url
    ]),
    ...(video.audio?.play_addr?.url_list || [])
  ]);
  const videoURLs = uniqueURLs([
    ...(video.play_addr?.url_list || []),
    ...(video.play_addr_h264?.url_list || []),
    ...(video.download_addr?.url_list || []),
    ...((video.bit_rate || []).flatMap(item => item?.play_addr?.url_list || []))
  ]);

  if (!audioURLs.length && !videoURLs.length) {
    throw new Error("The browser detail response did not contain a downloadable media URL.");
  }

    output = {
      title: String(detail.desc || detail.item_title || ""),
      audioUrl: audioURLs[0] || "",
      videoUrl: videoURLs[0] || "",
      audioUrls: audioURLs,
      videoUrls: videoURLs
    };
    break;
  } catch (error) {
    lastError = error;
    if (attempt < maxAttempts) {
      await new Promise(resolve => setTimeout(resolve, 1500));
    }
  }
}

if (output) {
  process.stdout.write(JSON.stringify(output));
} else {
  process.stderr.write(`${lastError?.message || String(lastError)}\n`);
  process.exitCode = 1;
}

async function lookupVideoDetail(browserPath, expectedId, timeout) {
  const browser = await chromium.launch({
    executablePath: browserPath,
    headless: process.env.DYT_BROWSER_HEADLESS !== "0",
    args: [
      "--disable-blink-features=AutomationControlled",
      "--disable-dev-shm-usage",
      "--no-first-run",
      "--no-default-browser-check"
    ]
  });

  try {
    const context = await browser.newContext({
      locale: "zh-CN",
      timezoneId: "Asia/Shanghai",
      viewport: { width: 1365, height: 768 },
      userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    });
    await context.addInitScript(() => {
      Object.defineProperty(navigator, "webdriver", { get: () => undefined });
    });

    const page = await context.newPage();
    const detailPromise = waitForVideoDetail(page, expectedId, timeout);
    await page.goto(`https://www.douyin.com/video/${expectedId}`, {
      waitUntil: "domcontentloaded",
      timeout
    });
    return await detailPromise;
  } finally {
    await browser.close().catch(() => {});
  }
}

function waitForVideoDetail(page, expectedId, timeout) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      page.off("response", onResponse);
      reject(new Error("Timed out waiting for Douyin video detail data."));
    }, timeout);

    async function onResponse(response) {
      if (!/\/aweme\/v1\/web\/aweme\/detail\//.test(response.url()) || response.status() !== 200) {
        return;
      }
      try {
        const data = await response.json();
        const detail = data?.aweme_detail || data?.awemeDetail;
        const id = String(detail?.aweme_id || detail?.awemeId || "");
        if (!detail || id !== expectedId) return;
        clearTimeout(timer);
        page.off("response", onResponse);
        resolve(detail);
      } catch {
        // Some matching responses are empty probes; keep waiting for real JSON.
      }
    }

    page.on("response", onResponse);
  });
}

function uniqueURLs(values) {
  return [...new Set(values.filter(value => typeof value === "string" && /^https?:\/\//.test(value)))];
}

function findBrowser() {
  const candidates = [
    process.env.DYT_BROWSER_EXE,
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
    "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser"
  ].filter(Boolean);
  return candidates.find(candidate => fs.existsSync(candidate)) || "";
}
