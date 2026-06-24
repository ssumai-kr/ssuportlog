const analyzeBtn = document.getElementById("analyze-btn");
const blogBtn = document.getElementById("blog-btn");
const statusEl = document.getElementById("status");

const tabBtns = document.querySelectorAll(".tab-btn");
const panels = {
  summary: document.getElementById("panel-summary"),
  blog: document.getElementById("panel-blog"),
};

const els = {
  summary: {
    loading: document.getElementById("summary-loading"),
    content: document.getElementById("summary-content"),
    empty: document.getElementById("summary-empty"),
    badge: document.getElementById("summary-badge"),
  },
  blog: {
    loading: document.getElementById("blog-loading"),
    content: document.getElementById("blog-content"),
    empty: document.getElementById("blog-empty"),
    badge: document.getElementById("blog-badge"),
  },
};

function switchTab(tab) {
  tabBtns.forEach((btn) => btn.classList.toggle("active", btn.dataset.tab === tab));
  Object.entries(panels).forEach(([key, panel]) => panel.classList.toggle("hidden", key !== tab));
}

tabBtns.forEach((btn) => btn.addEventListener("click", () => switchTab(btn.dataset.tab)));

function setLoading(tab, isLoading) {
  const { loading, content, empty } = els[tab];
  loading.classList.toggle("hidden", !isLoading);
  if (isLoading) {
    content.classList.add("hidden");
    empty.classList.add("hidden");
  }
}

function showResult(tab, html) {
  const { loading, content, empty } = els[tab];
  loading.classList.add("hidden");
  empty.classList.add("hidden");
  content.classList.remove("hidden");
  content.innerHTML = html;
}

function setBadge(tab, cached) {
  const badge = els[tab].badge;
  badge.textContent = cached ? "캐시됨 · API 호출 없음" : "새로 생성됨 · API 호출함";
  badge.className = "badge " + (cached ? "cached" : "fresh");
}

function getSelection() {
  const author = document.getElementById("author").value;
  const periods = Array.from(document.querySelectorAll('input[name="period"]:checked')).map(el => el.value);
  return { author, periods };
}

function setStatus(text) {
  statusEl.textContent = text;
}

const PALETTE = ["#4f46e5", "#16a34a", "#dc2626", "#d97706", "#0891b2", "#9333ea", "#be185d"];
const authorColors = new Map();
const commitRowByHash = new Map();

function colorForAuthor(author) {
  if (!authorColors.has(author)) {
    authorColors.set(author, PALETTE[authorColors.size % PALETTE.length]);
  }
  return authorColors.get(author);
}

async function loadCommitGraph() {
  const graphEl = document.getElementById("commit-graph");
  const legendEl = document.getElementById("commit-graph-legend");
  const countEl = document.getElementById("commit-graph-count");
  try {
    const res = await fetch("/api/commits");
    const commits = await res.json();
    countEl.textContent = `(${commits.length})`;

    commits.forEach((c) => colorForAuthor(c.author));
    legendEl.innerHTML = Array.from(authorColors.entries()).map(([author, color]) => `
      <span class="legend-item"><span class="legend-dot" style="background:${color}"></span>${author}</span>
    `).join("");

    const rowsHtml = commits.map((c) => {
      const color = colorForAuthor(c.author);
      const subject = c.subject.replace(/</g, "&lt;");
      return `<div class="commit-row" data-hash="${c.hash}" title="${c.author} · ${c.date} · ${subject}">
        <span class="commit-dot" style="background:${color}"></span>
        <span class="commit-date">${c.date.slice(5)}</span>
        <span class="commit-subject">${subject}</span>
      </div>`;
    }).join("");
    graphEl.innerHTML = '<div class="commit-graph-line"></div>' + rowsHtml;

    commitRowByHash.clear();
    graphEl.querySelectorAll(".commit-row").forEach((row) => {
      commitRowByHash.set(row.dataset.hash, row);
    });
  } catch (err) {
    graphEl.innerHTML = '<div class="commit-row">커밋 그래프를 불러오지 못했습니다.</div>';
  }
}

function highlightCommits(hashes) {
  commitRowByHash.forEach((row) => row.classList.remove("highlighted"));
  let firstRow = null;
  (hashes || []).forEach((hash) => {
    const row = commitRowByHash.get(hash);
    if (row) {
      row.classList.add("highlighted");
      if (!firstRow) firstRow = row;
    }
  });
  if (firstRow) firstRow.scrollIntoView({ block: "center", behavior: "smooth" });
}

loadCommitGraph();

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  const contentType = res.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    if (res.status >= 500) {
      throw new Error("서버가 요청 처리 중 다운됐습니다 (메모리 부족 등). 잠시 후 다시 시도해주세요.");
    }
    throw new Error(`서버 응답이 올바르지 않습니다 (status ${res.status}).`);
  }

  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "요청에 실패했습니다.");
  return data;
}

analyzeBtn.addEventListener("click", async () => {
  const { author, periods } = getSelection();
  if (!author || periods.length === 0) {
    setStatus("작성자와 기간을 모두 선택해주세요.");
    return;
  }

  switchTab("summary");
  analyzeBtn.disabled = true;
  setLoading("summary", true);
  setStatus("분석 중...");
  try {
    const data = await postJSON("/api/analyze", { author, periods });
    showResult("summary", marked.parse(data.content));
    setBadge("summary", data.cached);
    setStatus(`커밋 ${data.commit_count}개 기반 분석 완료`);
    highlightCommits(data.commit_hashes);
    blogBtn.disabled = false;
  } catch (err) {
    setLoading("summary", false);
    els.summary.empty.classList.remove("hidden");
    setStatus("오류: " + err.message);
  } finally {
    analyzeBtn.disabled = false;
  }
});

blogBtn.addEventListener("click", async () => {
  const { author, periods } = getSelection();

  switchTab("blog");
  blogBtn.disabled = true;
  setLoading("blog", true);
  setStatus("블로그 초안 생성 중...");
  try {
    const data = await postJSON("/api/blog", { author, periods });
    showResult("blog", marked.parse(data.content));
    setBadge("blog", data.cached);
    setStatus("블로그 초안 생성 완료");
    highlightCommits(data.commit_hashes);
  } catch (err) {
    setLoading("blog", false);
    els.blog.empty.classList.remove("hidden");
    setStatus("오류: " + err.message);
  } finally {
    blogBtn.disabled = false;
  }
});

document.getElementById("copy-blog-btn").addEventListener("click", () => {
  navigator.clipboard.writeText(els.blog.content.innerText);
  setStatus("블로그 초안이 클립보드에 복사되었습니다.");
});
