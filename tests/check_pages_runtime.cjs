/* Run after prepare_github_pages.py. Verify the browser adapter against real data. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const root = path.resolve(__dirname, "..", ".tmp-pages-site");
const base = "https://heart06215.github.io/powang-demo/";
const fetchedFiles = [];
const context = {
  URL, Request, Response, Set, Map, Object, Number, String, Error,
  location: new URL(base),
  document: {currentScript: {src: base + "pages-runtime.js"}, addEventListener() {}},
  MutationObserver: class { observe() {} },
  window: {fetch: async (input) => {
    const url = new URL(String(input), base);
    const local = path.join(root, url.pathname.slice("/powang-demo/".length));
    fetchedFiles.push(path.relative(root, local).replaceAll("\\", "/"));
    return new Response(fs.readFileSync(local));
  }},
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(root, "pages-runtime.js"), "utf8"), context);

/** @param {string} route @param {RequestInit} [options] @returns {Promise<object>} */
async function request(route, options) {
  const response = await context.window.fetch(route, options);
  return response.json();
}

/** @returns {Promise<void>} */
async function main() {
  const videos = (await request("/api/videos")).data.videos;
  assert.equal(videos.length, 2);
  assert.deepEqual(fetchedFiles, ["data/videos.json"]);
  const firstReport = (await request("/api/research/report")).data;
  assert.equal(firstReport.sample_count, 7199);
  assert.ok(!fetchedFiles.some((name) => name.includes("comments-")));
  const bvid = videos[0].bvid;
  const analysis = (await request(`/api/analysis/${bvid}`)).data;
  assert.equal(analysis.total, 4267);
  const first = (await request(`/api/comments?bvid=${bvid}&size=96&page=1`)).data;
  const second = (await request(`/api/comments?bvid=${bvid}&size=96&page=2`)).data;
  assert.equal(first.total, 4267);
  assert.equal(first.items.length, 96);
  assert.equal(new Set([...first.items, ...second.items].map((row) => String(row.rpid))).size, 192);
  const filtered = (await request(`/api/comments?bvid=${bvid}&category=水军&size=200`)).data;
  assert.ok(filtered.items.every((row) => row.category === "水军"));
  const keyword = first.items[0].text.slice(0, 3);
  const searched = (await request(`/api/comments?bvid=${bvid}&q=${encodeURIComponent(keyword)}`)).data;
  assert.ok(searched.items.length && searched.items.every((row) => row.text.toLowerCase().includes(keyword.toLowerCase())));
  const anchors = (await request("/api/anchors")).data;
  assert.equal(anchors.count, 107);
  const queue = (await request(`/api/review/queue?bvid=${bvid}&size=50`)).data;
  assert.equal(queue.items.length, 50);
  const labeled = new Set(anchors.anchors.filter((row) => row.bvid === bvid).map((row) => String(row.rpid)));
  assert.ok(queue.items.every((row) => !labeled.has(String(row.rpid))));
  assert.equal((await request("/api/anchors", {method: "POST"})).success, false);
  assert.equal((await request("/api/agent/chat", {method: "POST"})).success, false);
  const report = (await request("/powang-demo/api/research/report")).data;
  assert.equal(report.sample_count, 7199);
  assert.equal(report.methods.find((method) => method.id === "llm_zeroshot").target.accuracy, 0.7);
  assert.ok(!( "accuracy" in report.methods.find((method) => method.id === "annotated").result));
  for (const limit of [240, 520]) {
    const graph = await request(`/api/graph?comments=${limit}`);
    assert.ok(graph.success && graph.data.nodes.length && graph.data.edges.length);
  }
  console.log("Pages smoke: pagination, filters, review, targets, graphs and read-only operations passed");
}
main().catch((error) => { console.error(error); process.exitCode = 1; });
