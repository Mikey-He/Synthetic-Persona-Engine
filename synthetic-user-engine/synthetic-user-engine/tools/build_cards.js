// Builds persona cards from answer files through tools/persona-builder.html itself, so a
// card made here is exactly the card a researcher would download from the page.
//   node tools/build_cards.js                       every file in data/answers, plus the blank and full cards
//   node tools/build_cards.js data/answers/joy.json  one answer file
// Needs Playwright: set PLAYWRIGHT to its folder if it is not installed next to this repo,
// e.g. PLAYWRIGHT=C:/github/synthetic-uat-platform/uat-platform/node_modules/playwright
const path = require("path");
const fs = require("fs");
const { chromium } = require(process.env.PLAYWRIGHT || "playwright");

const ROOT = path.resolve(__dirname, "..");
const PAGE = "file:///" + path.join(ROOT, "tools", "persona-builder.html").replace(/\\/g, "/");
const OUT = path.join(ROOT, "data", "personas");
const args = process.argv.slice(2);
const files = args.length ? args : fs.readdirSync(path.join(ROOT, "data", "answers"))
  .filter((f) => f.endsWith(".json")).map((f) => path.join(ROOT, "data", "answers", f));

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(PAGE);
  const build = async (label, text, type, fileName) => {
    const card = await page.evaluate(([text, type]) => {
      const b = window.__sueBuilder;
      b.load(text ? b.parseAnswers(text) : null, type);
      return b.buildCard();
    }, [text, type]);
    fs.writeFileSync(path.join(OUT, fileName), JSON.stringify(card, null, 2) + "\n", "utf8");
    const counts = {};
    card.items.forEach((i) => { counts[i.result] = (counts[i.result] || 0) + 1; });
    const t = card.tendency;
    console.log(`${label} -> data/personas/${fileName}  risk ${t.risk.level}, patience ${t.patience.level}, ` +
      `find ${t.detailFind.level}, check ${t.detailCheck.level}, care ${card.goal.care.map((k) => k.id).join("+") || "none"}` +
      `${card.persona.calibrated ? ", calibrated" : ""}\n    ${JSON.stringify(counts)}`);
  };
  for (const f of files) {
    const name = path.basename(f, ".json");
    await build(path.relative(ROOT, f), fs.readFileSync(f, "utf8"), "normal", name + ".json");
  }
  if (!args.length) {
    await build("blank", null, "blank", "blank-card.json");
    await build("full", null, "full", "full-card.json");
  }
  await browser.close();
  if (errors.length) { console.error("page errors:\n" + errors.join("\n")); process.exit(1); }
})();
