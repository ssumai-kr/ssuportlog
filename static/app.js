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

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
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
