/* Native SVG charts keep public data readable without a CDN or chart runtime. */
(() => {
  "use strict";
  const data = window.GovernanceData;
  const categories = ["赞美", "贬低", "水军", "无意义", "社区对骂", "中立"];
  const categoryClasses = ["praise", "blame", "shui", "noise", "feud", "neutral"];
  const state = { year: 2024, trend: "scale", videos: [], loaded: false, chatController: undefined, toastTimer: undefined };

  /** @param {string} id @returns {HTMLElement} */
  function byId(id) { return document.getElementById(id); }
  /** @param {unknown} value @returns {string} */
  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]);
  }
  /** @param {number} value @returns {string} */
  function number(value) { return new Intl.NumberFormat("zh-CN").format(value); }
  /** @param {string} message @returns {void} */
  function toast(message) {
    clearTimeout(state.toastTimer);
    byId("appToast").textContent = message;
    byId("appToast").hidden = false;
    state.toastTimer = setTimeout(() => { byId("appToast").hidden = true; }, 6000);
  }
  /** @param {string} url @param {RequestInit} [options] @returns {Promise<object>} */
  async function request(url, options = {}) {
    const response = await fetch(url, { ...options, signal: options.signal ?? AbortSignal.timeout(15000) });
    const payload = await response.json();
    if (!response.ok || !payload.success) throw new Error("服务暂未返回可用数据");
    return payload.data;
  }
  /** @returns {void} */
  function renderEconomy() {
    const current = data.economy.find((row) => row.year === state.year);
    byId("gdpShare").innerHTML = `${current.share.toFixed(1)}<span>%</span>`;
    byId("donutFill").setAttribute("stroke-dasharray", `${current.share} 100`);
    byId("gdpDonut").setAttribute("aria-label", `${current.year}年数字经济占GDP的${current.share}%`);
    byId("donutYear").textContent = `${current.year} 年`;
    byId("digitalLegend").textContent = `${current.share.toFixed(1)}%`;
    byId("otherLegend").textContent = `${(100 - current.share).toFixed(1)}%`;
    byId("economyScale").textContent = current.scale.toFixed(1);
    byId("shareChange").innerHTML = `+${current.shareChange.toFixed(1)}<small> 个百分点</small>`;
    byId("shareSource").textContent = `来源：${current.source} ↗`;
    byId("shareSource").href = current.url;
    renderGrowth();
  }
  /** @returns {void} */
  function renderGrowth() {
    const isScale = state.trend === "scale";
    const current = data.economy.find((row) => row.year === state.year);
    const first = data.economy[0];
    const unit = isScale ? "万亿元" : "%";
    byId("growthValue").innerHTML = `${current[state.trend].toFixed(1)}<small> ${unit}</small>`;
    byId("growthDescription").textContent = `${current.year} 年${isScale ? "数字经济规模" : "占 GDP 比重"}`;
    byId("growthBadge").textContent = isScale
      ? `较 2020 年 +${((current.scale / first.scale - 1) * 100).toFixed(1)}%`
      : `较 2020 年 +${(current.share - first.share).toFixed(1)} 个百分点`;
    byId("trendLegend").textContent = isScale ? "数字经济规模（万亿元）" : "占 GDP 比重（%）";
    byId("growthChart").setAttribute("aria-label", data.economy.map((row) => `${row.year}年${row[state.trend]}${unit}`).join("；"));
    const chartWidth = Math.max(220, Math.round(byId("growthChart").clientWidth));
    const bounds = { left: 48, right: chartWidth - 28, top: 32, bottom: 212 };
    const minimum = isScale ? 30 : 35;
    const maximum = isScale ? 65 : 45;
    const axisValues = isScale ? [30, 40, 50, 60] : [35, 37.5, 40, 42.5, 45];
    const points = data.economy.map((row, index) => ({
      x: bounds.left + index * (bounds.right - bounds.left) / (data.economy.length - 1),
      y: bounds.bottom - (row[state.trend] - minimum) / (maximum - minimum) * (bounds.bottom - bounds.top),
      value: row[state.trend], year: row.year
    }));
    const line = points.map((point, index) => `${index === 0 ? "M" : "L"}${point.x},${point.y}`).join(" ");
    const grid = axisValues.map((value) => {
      const y = bounds.bottom - (value - minimum) / (maximum - minimum) * (bounds.bottom - bounds.top);
      return `<line class="chart-grid" x1="${bounds.left}" y1="${y}" x2="${bounds.right}" y2="${y}"/><text class="chart-label" x="36" y="${y + 4}" text-anchor="end">${value}</text>`;
    }).join("");
    byId("growthChart").innerHTML = `<svg viewBox="0 0 ${chartWidth} 250" preserveAspectRatio="xMidYMid meet" aria-hidden="true">${grid}<path class="chart-area" d="${line} L${bounds.right},${bounds.bottom} L${bounds.left},${bounds.bottom} Z"/><path class="chart-line" d="${line}"/>${points.map((point, index) => {
      const showValue = chartWidth >= 420 || index === 0 || index === points.length - 1 || point.year === state.year;
      return `<circle class="chart-point${point.year === state.year ? " active" : ""}" cx="${point.x}" cy="${point.y}" r="${point.year === state.year ? 5 : 3.5}"/>${showValue ? `<text class="chart-value" x="${point.x}" y="${point.y - 14}" text-anchor="middle">${point.value.toFixed(1)}${isScale ? "" : "%"}</text>` : ""}<text class="chart-label" x="${point.x}" y="240" text-anchor="middle">${point.year}</text>`;
    }).join("")}</svg>`;
  }
  /** @returns {void} */
  function renderSources() {
    byId("economyTable").innerHTML = data.economy.map((row) => `<tr><th scope="row">${row.year}</th><td>${row.scale.toFixed(1)}</td><td>${row.share.toFixed(1)}%</td><td><a href="${row.url}" target="_blank" rel="noopener noreferrer">${escapeHtml(row.source)} ↗</a></td></tr>`).join("");
    byId("lawList").innerHTML = data.laws.map((law) => `<article class="law-row"><div class="law-date">${law.date}<small>施行日期</small></div><div><h4>${law.title}</h4><div class="law-meta"><span class="tag">${law.topic}</span><span>${law.issuer} · ${law.articles}</span></div><p>${law.description}</p></div><a class="text-link" href="${law.url}" target="_blank" rel="noopener noreferrer" aria-label="阅读${law.title}官方原文">官方原文 ↗</a></article>`).join("");
    byId("competitionReferences").innerHTML = data.competitions.map((item) => `<article><span>${item.contest}</span><span class="tag">${item.award}</span><h4><a href="${item.url}" target="_blank" rel="noopener noreferrer">${item.title} ↗</a></h4><p>${item.takeaway}</p></article>`).join("");
  }
  /** @param {object[]} videos @returns {Object<string, number>} */
  function countsFor(videos) {
    return Object.fromEntries(categories.map((category) => [category, videos.reduce((sum, video) => sum + (Number(video.analysis?.[category]) || 0), 0)]));
  }
  /** @returns {object[]} */
  function selectedVideos() {
    const selected = byId("communitySelect").value;
    return state.videos.filter((video) => selected === "all" || video.bvid === selected);
  }
  /** @returns {void} */
  function renderCommunities() {
    const videos = selectedVideos();
    const counts = countsFor(videos);
    const total = Object.values(counts).reduce((sum, value) => sum + value, 0);
    const samples = videos.reduce((sum, video) => sum + (Number(video.corpus_count) || 0), 0);
    byId("communitySummary").textContent = `${videos.map((video) => video.community || video.name).join(" / ") || "尚未配置社区"} · 已分类 ${number(total)} 条 / 采集 ${number(samples)} 条`;
    byId("clueCount").textContent = total ? number(counts["水军"] + counts["社区对骂"]) : "—";
    if (!total) {
      byId("categoryBars").innerHTML = '<div class="empty-state">尚无分类结果。<a href="/label">前往人工标注与分析</a>，建立研究样本。</div>';
      byId("evidenceCards").innerHTML = '<div class="empty-state">分析完成后，这里将呈现来自原始语料的代表性评论与分类依据。</div>';
      return;
    }
    byId("categoryBars").innerHTML = categories.map((category, index) => {
      const percent = counts[category] / total * 100;
      return `<div class="category-row category-${categoryClasses[index]}"><span>${category}</span><div class="category-track" aria-hidden="true"><div class="category-fill" style="width:${percent.toFixed(2)}%"></div></div><strong>${number(counts[category])}</strong><span>${percent.toFixed(1)}%</span></div>`;
    }).join("");
    renderEvidence(videos);
  }
  /** @param {object[]} videos @returns {void} */
  function renderEvidence(videos) {
    const candidates = [];
    const seen = new Set();
    // Round-robin across videos so one large community does not fill the entire evidence row.
    for (const category of ["社区对骂", "水军", "中立"]) {
      for (const video of videos) {
        const comment = video.representative?.[category]?.find((row) => row.text && !seen.has(`${video.bvid}:${row.rpid}`));
        if (!comment) continue;
        seen.add(`${video.bvid}:${comment.rpid}`);
        candidates.push({ video, comment, category });
      }
    }
    byId("evidenceCards").innerHTML = candidates.slice(0, 3).map(({ video, comment, category }) => {
      const query = new URLSearchParams({ bvid: video.bvid, category, q: Array.from(comment.text).slice(0, 30).join("") });
      const confidence = Number(comment.confidence);
      const confidenceLabel = Number.isFinite(confidence) ? `模型置信度 ${(confidence * 100).toFixed(0)}%` : "模型分类";
      return `<article class="evidence-card"><div class="evidence-top"><span class="tag neutral">${escapeHtml(category)} · 待核验</span><span>${confidenceLabel}</span></div><blockquote>${escapeHtml(comment.text)}</blockquote><details><summary>查看全文与分类依据</summary><p>${escapeHtml(comment.text)}</p><p>模型依据：${escapeHtml(comment.reason || "该条未提供分类说明，请回到原始评论核验。")}</p><p>样本标识：${escapeHtml(comment.rpid || "未提供")} · ${escapeHtml(video.bvid)}</p></details><a class="evidence-link" href="/comments?${escapeHtml(query.toString())}"><span>${escapeHtml(video.community || "研究社区")} · ${escapeHtml(video.name)}</span><span>追溯样本 ↗</span></a></article>`;
    }).join("") || '<div class="empty-state">该社区尚无代表性评论。<a href="/comments">查看完整评论证据库</a>。</div>';
  }
  /** @returns {Promise<void>} */
  async function loadLocalData() {
    byId("retryData").disabled = true;
    byId("dataError").hidden = true;
    byId("connectionState").textContent = "正在连接数据";
    try {
      const result = await request("/api/videos");
      state.videos = result.videos || [];
      state.loaded = true;
      const sampleCount = state.videos.reduce((sum, video) => sum + (Number(video.corpus_count) || 0), 0);
      const analyzed = Object.values(countsFor(state.videos)).reduce((sum, value) => sum + value, 0);
      byId("sampleCount").textContent = number(sampleCount);
      byId("analyzedCount").textContent = number(analyzed);
      byId("anchorCount").textContent = number(state.videos.reduce((sum, video) => sum + (Number(video.anchor_count) || 0), 0));
      byId("communityCount").textContent = number(new Set(state.videos.map((video) => video.community).filter(Boolean)).size);
      byId("communityNames").textContent = [...new Set(state.videos.map((video) => video.community).filter(Boolean))].join(" / ") || "尚未配置社区";
      byId("analysisCoverage").textContent = sampleCount ? `采集样本覆盖率 ${(analyzed / sampleCount * 100).toFixed(1)}%` : "暂无采集样本";
      byId("connectionState").innerHTML = '<span class="status-dot"></span>本地数据已连接';
      const previousSelection = byId("communitySelect").value;
      byId("communitySelect").innerHTML = '<option value="all">全部研究社区</option>' + state.videos.map((video) => `<option value="${escapeHtml(video.bvid)}">${escapeHtml(video.community || "社区")} · ${escapeHtml(video.name)}</option>`).join("");
      if (state.videos.some((video) => video.bvid === previousSelection)) byId("communitySelect").value = previousSelection;
      renderCommunities();
    } catch {
      state.loaded = false;
      byId("connectionState").textContent = "本地数据连接失败";
      byId("dataError").hidden = false;
      byId("dataErrorText").textContent = "暂时无法读取本地评论数据，请确认项目服务运行后重新连接。公开经济数据仍可浏览。";
      byId("communitySummary").textContent = "本地评论数据暂不可用";
      byId("categoryBars").innerHTML = '<div class="empty-state">数据读取失败，请点击上方“重新连接”。</div>';
      byId("evidenceCards").innerHTML = '<div class="empty-state">连接恢复后将显示真实语料中的评论证据。</div>';
      for (const id of ["sampleCount", "analyzedCount", "anchorCount", "communityCount", "clueCount"]) byId(id).textContent = "—";
      byId("analysisCoverage").textContent = "数据暂不可用";
    } finally { byId("retryData").disabled = false; }
  }
  /** @param {string} filename @param {string} content @returns {void} */
  function downloadText(filename, content) {
    const url = URL.createObjectURL(new Blob(["\uFEFF", content], { type: "text/markdown;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url; link.download = filename; document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    toast("已生成研究文件，可在浏览器下载记录中查看。");
  }
  /** @param {boolean} policyOnly @returns {void} */
  function exportResearch(policyOnly) {
    const date = new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Shanghai" }).format(new Date());
    const lines = ["# 破妄 · 网络生态治理与立法研究", "", `导出日期：${date}（北京时间）`, "", "## 研究定位", "以社区评论的语境分类、证据追溯和人工复核，辅助发现网络生态治理问题，为规则评估与网络立法研究提供素材。", ""];
    if (!policyOnly) {
      lines.push("## 本地样本概况", state.loaded ? "数据来源：本项目本地语料与已保存的模型分析。" : "本地数据未成功加载，本次导出不包含样本统计。", "");
      if (state.loaded) for (const video of state.videos) lines.push(`- ${video.name}（${video.community || "研究社区"}，${video.bvid}）：采集 ${video.corpus_count || 0} 条；分类 ${Object.values(countsFor([video])).reduce((sum, value) => sum + value, 0)} 条；人工锚定 ${video.anchor_count || 0} 条。`, `  分类统计：${categories.map((category) => `${category} ${video.analysis?.[category] || 0}`).join("；")}。`);
      lines.push("", "## 数字经济背景", "中国信通院测算口径（数字产业化与产业数字化），历年公开发布值，未作经济普查回溯调整。", ...data.economy.map((row) => `- ${row.year} 年：规模 ${row.scale} 万亿元，占 GDP ${row.share}%。来源：${row.source} ${row.url}`), "", "国家统计局口径：2024 年数字经济核心产业增加值 14.0891 万亿元，占 GDP 10.5%，与上述统计范围不同。", "来源：https://www.stats.gov.cn/sj/zxfbhjd/202512/t20251230_1962177.html", "");
    }
    lines.push("## 待论证的研究问题", "1. 如何结合语境与人工复核，区分正常批评、玩梗与人身攻击？", "2. 疑似刷评需要哪些文本之外的证据，才能验证是否存在组织化操纵？", "3. 平台如何建立有解释、可复核的评论治理流程，保护用户合法表达？", "4. 现有规则在隐晦攻击、跨社区传播和证据留存方面有哪些需要进一步调研的难点？", "", "## 证据整理提纲", "- 界定样本范围、采集时间与去重方法；记录样本代表性和选择偏差。", "- 留存评论标识、来源视频、上下文、分类理由、人工复核意见和修订记录。", "- 逐项关联现行规则，明确事实缺口，开展实证与规范论证。", "- 提出研究建议，并评估对合法表达、隐私保护和申诉救济的影响。", "", "## 官方规则参考", ...data.laws.map((law) => `- ${law.title}（${law.date} 施行，参考 ${law.articles}）：${law.url}`), "", "## 研究边界", "本项目目前研究已配置的视频社区样本，不代表全网。模型标签与置信度不是违法认定、付费刷评证明或准确率。规则关联由研究人员整理，不是自动法律裁决。研究提纲需要人工核查与后续论证。", "", `公开资料核验日期：${data.verifiedOn}。`);
    downloadText(`破妄-${policyOnly ? "立法研究提纲" : "治理研究摘要"}-${date}.md`, lines.join("\n"));
  }
  /** @param {string} role @param {string} message @returns {HTMLElement} */
  function addMessage(role, message) {
    byId("chatMessages").querySelector(".assistant-welcome")?.remove();
    const node = document.createElement("div"); node.className = `chat-message ${role}`;
    const label = document.createElement("small"); label.textContent = role === "user" ? "研究提问" : "破妄 · AI 助手";
    const body = document.createElement("span"); body.textContent = message;
    node.append(label, body); byId("chatMessages").append(node); byId("chatMessages").scrollTop = byId("chatMessages").scrollHeight;
    return node;
  }
  /** @param {SubmitEvent} event @returns {Promise<void>} */
  async function sendQuestion(event) {
    event.preventDefault();
    const question = byId("chatQuestion").value.trim();
    if (!question || state.chatController) return;
    addMessage("user", question);
    const reply = addMessage("assistant", "正在分析本地研究数据…");
    const controller = new AbortController(); state.chatController = controller;
    byId("sendQuestion").disabled = true; byId("stopQuestion").hidden = false;
    byId("chatForm").setAttribute("aria-busy", "true");
    let timedOut = false;
    const timeout = setTimeout(() => { timedOut = true; controller.abort(); }, 60000);
    try {
      const result = await request("/api/agent/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }), signal: controller.signal });
      reply.querySelector("span").textContent = typeof result.answer === "string" ? result.answer : "模型未返回文本回答，请调整问题后重试。";
      byId("chatQuestion").value = "";
    } catch {
      reply.classList.add("error");
      reply.querySelector("span").textContent = controller.signal.aborted
        ? (timedOut ? "回答等待超时。问题已保留，可以重试或缩小问题范围。" : "已停止等待本次回答。问题已保留，可修改后重新发送。")
        : "暂时无法获取回答，请检查模型服务配置后重试。问题已保留。";
    } finally {
      clearTimeout(timeout); state.chatController = undefined;
      byId("sendQuestion").disabled = false; byId("stopQuestion").hidden = true; byId("chatForm").removeAttribute("aria-busy");
      byId("chatMessages").scrollTop = byId("chatMessages").scrollHeight;
    }
  }
  /** @returns {void} */
  function bindEvents() {
    byId("economyYear").addEventListener("change", (event) => { state.year = Number(event.target.value); renderEconomy(); });
    document.querySelectorAll("[data-trend]").forEach((button) => button.addEventListener("click", () => {
      state.trend = button.dataset.trend;
      document.querySelectorAll("[data-trend]").forEach((item) => { item.classList.toggle("selected", item === button); item.setAttribute("aria-pressed", String(item === button)); });
      renderGrowth();
    }));
    byId("communitySelect").addEventListener("change", renderCommunities);
    byId("retryData").addEventListener("click", loadLocalData);
    byId("exportReport").addEventListener("click", () => exportResearch(false));
    byId("exportPolicy").addEventListener("click", () => exportResearch(true));
    document.querySelectorAll('a[href="#dataSources"]').forEach((link) => link.addEventListener("click", () => { byId("sourceDetails").open = true; }));
    byId("chatForm").addEventListener("submit", sendQuestion);
    byId("chatQuestion").addEventListener("keydown", (event) => { if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); byId("chatForm").requestSubmit(); } });
    byId("stopQuestion").addEventListener("click", () => state.chatController?.abort());
    byId("clearChat").addEventListener("click", () => { state.chatController?.abort(); byId("chatMessages").replaceChildren(); byId("chatQuestion").focus(); });
    document.querySelectorAll("[data-prompt]").forEach((button) => button.addEventListener("click", () => { byId("chatQuestion").value = button.dataset.prompt; byId("chatQuestion").focus(); }));

  }
  state.year = Number(byId("economyYear").value);
  renderEconomy(); renderSources(); bindEvents(); loadLocalData();
  new ResizeObserver(renderGrowth).observe(byId("growthChart"));
})();
