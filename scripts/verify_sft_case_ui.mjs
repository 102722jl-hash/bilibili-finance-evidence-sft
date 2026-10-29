import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require("C:/Users/LL/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright");

const root = process.cwd();
const output = path.join(root, "reports", "v4.1-ui");
fs.mkdirSync(output, { recursive: true });
const browser = await chromium.launch({
  executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
  headless: true,
});
const results = [];

for (const viewport of [
  { name: "desktop", width: 1440, height: 1000 },
  { name: "mobile", width: 390, height: 844 },
]) {
  const page = await browser.newPage({ viewport });
  const errors = [];
  page.on("console", message => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("http://127.0.0.1:8765/sft-case-ui-demo.html", { waitUntil: "networkidle" });
  const versions = {};
  for (const version of ["merged", "v41", "v5"]) {
    await page.click(`[data-dataset-key="${version}"]`);
    await page.waitForTimeout(50);
    const cases = {};
    const caseIds = await page.locator("[data-case-id]").evaluateAll(nodes => nodes.map(node => node.dataset.caseId));
    const expectedCases = version === "merged" ? 20 : 10;
    if (caseIds.length !== expectedCases) throw new Error(`${version}: expected ${expectedCases} cases, got ${caseIds.length}`);
    for (const caseId of caseIds) {
      await page.click(`[data-case-id="${caseId}"]`);
      await page.waitForTimeout(30);
      const trainingTab = page.locator('[data-view="training"]');
      await trainingTab.click();
      cases[caseId] = await page.evaluate(({ versionKey, currentCaseId }) => ({
        title: document.querySelector("h1")?.textContent,
        eyebrow: document.querySelector(".eyebrow")?.textContent,
        badges: document.querySelector(".badges")?.textContent,
        nodeCount: document.querySelectorAll("#lanes .node").length,
        laneStepCounts: [...document.querySelectorAll("#lanes .lane")].map(lane => lane.querySelectorAll(".node").length),
        qaCount: document.querySelectorAll("#qaList .qa-button").length,
        hasVersion: document.querySelector("#qaDetail")?.textContent.includes(`${versionKey === "v5" || (versionKey === "merged" && currentCaseId.startsWith("CASE-V5-")) ? "V5" : "V4.1"} 监督目标`),
        hasAbstain: document.querySelector("#qaDetail")?.textContent.includes("ABSTAIN"),
        horizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      }), { versionKey: version, currentCaseId: caseId });
      const sourceTab = page.locator('[data-view="sources"]');
      await sourceTab.click();
      cases[caseId].sourceCards = await page.locator("#sourcesContent .source-card").count();
    }
    versions[version] = cases;
  }
  await page.screenshot({ path: path.join(output, `${viewport.name}.png`), fullPage: true });
  results.push({ viewport, versions, errors });
  await page.close();
}

await browser.close();
fs.writeFileSync(path.join(output, "verification.json"), JSON.stringify(results, null, 2));
for (const result of results) {
  if (result.errors.length) throw new Error(`${result.viewport.name}: console errors: ${result.errors.join("; ")}`);
  for (const [version, cases] of Object.entries(result.versions)) {
    for (const [caseId, row] of Object.entries(cases)) {
      if (!row.hasVersion || !row.hasAbstain || row.qaCount !== 9 || row.nodeCount < 23) throw new Error(`${result.viewport.name}/${version}/${caseId}: UI incomplete`);
      const isV5Case = version === "v5" || (version === "merged" && caseId.startsWith("CASE-V5-"));
      if (isV5Case && !row.badges.includes("待人工审核")) throw new Error(`${result.viewport.name}/${caseId}: V5 review status hidden`);
      if (isV5Case && caseId.includes("LEHUA") && !row.eyebrow.includes("LEHUA_CAPITAL_CYCLE")) throw new Error(`${result.viewport.name}/${caseId}: parent cluster hidden`);
      if (row.horizontalOverflow) throw new Error(`${result.viewport.name}/${version}/${caseId}: horizontal overflow`);
    }
  }
}
console.log(JSON.stringify(results));
