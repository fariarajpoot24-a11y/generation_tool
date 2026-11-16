(() => {
  const $ = (id) => document.getElementById(id);

  const form = $("search-form");
  const searchBtn = $("search-btn");
  const message = $("message");
  const resultsPanel = $("results");
  const rowsEl = $("rows");
  const countEl = $("count");
  const visibleNote = $("visible-note");
  const fWebsite = $("f-website");
  const fPhone = $("f-phone");

  let allResults = [];

  /* ---------- helpers ---------- */
  function esc(value) {
    const div = document.createElement("div");
    div.textContent = value == null ? "" : String(value);
    return div.innerHTML;
  }

  function safeUrl(url) {
    try {
      const u = new URL(url);
      return u.protocol === "http:" || u.protocol === "https:" ? u.href : "";
    } catch {
      return "";
    }
  }

  function showMessage(text, type = "error") {
    message.textContent = text;
    message.className = `banner banner-${type}`;
    message.hidden = false;
  }

  function clearMessage() {
    message.hidden = true;
    message.textContent = "";
  }

  function visibleResults() {
    return allResults.filter(
      (r) => (!fWebsite.checked || r.website) && (!fPhone.checked || r.phone)
    );
  }

  /* ---------- rendering ---------- */
  function render() {
    const rows = visibleResults();
    countEl.textContent = allResults.length;
    visibleNote.textContent =
      rows.length !== allResults.length ? `(showing ${rows.length})` : "";

    const empty = '<td class="empty">—</td>';

    rowsEl.innerHTML = rows
      .map((r) => {
        const site = safeUrl(r.website);
        const map = safeUrl(r.maps_url);
        const rating = r.rating !== "" ? `${esc(r.rating)} <small class="muted">(${esc(r.reviews || 0)})</small>` : "";
        const closed = r.status && r.status !== "Operational";
        return `<tr>
          <td class="name"><strong>${esc(r.name)}</strong><small>${esc(r.category)}</small></td>
          <td>${esc(r.address)}</td>
          ${r.phone ? `<td>${esc(r.phone)}</td>` : empty}
          ${site ? `<td><a href="${esc(site)}" target="_blank" rel="noopener noreferrer">${esc(site.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, ""))}</a></td>` : empty}
          <td class="num">${rating || "—"}</td>
          <td>${r.status ? `<span class="pill${closed ? " closed" : ""}">${esc(r.status)}</span>` : "—"}</td>
          <td>${map ? `<a href="${esc(map)}" target="_blank" rel="noopener noreferrer">Open</a>` : "—"}</td>
        </tr>`;
      })
      .join("");

    resultsPanel.hidden = allResults.length === 0;
    $("export-csv").disabled = $("export-xlsx").disabled = rows.length === 0;
  }

  /* ---------- search ---------- */
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearMessage();
    searchBtn.disabled = true;
    searchBtn.textContent = "Scraping...";

    try {
      const res = await fetch("/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          keyword: $("keyword").value,
          location: $("location").value,
          max_results: $("max-results").value,
        }),
      });
      const start = await res.json();
      if (!res.ok) throw new Error(start.error || "Search failed.");

      // Poll until the background scrape finishes.
      let data;
      for (;;) {
        await sleep(1500);
        const r = await fetch(`/api/status/${start.job_id}`);
        data = await r.json();
        if (!r.ok) throw new Error(data.error || "Search failed.");
        if (data.state === "running") showMessage(data.message, "info");
        else break;
      }
      if (data.state === "error") throw new Error(data.error);

      clearMessage();
      allResults = data.results;
      fWebsite.checked = fPhone.checked = false;
      render();

      if (allResults.length === 0) {
        showMessage("No businesses found. Try a broader business type or another location.", "info");
      }
    } catch (err) {
      allResults = [];
      render();
      showMessage(err.message);
    } finally {
      searchBtn.disabled = false;
      searchBtn.textContent = "Search businesses";
    }
  });

  fWebsite.addEventListener("change", render);
  fPhone.addEventListener("change", render);

  /* ---------- export ---------- */
  async function exportAs(format) {
    clearMessage();
    const rows = visibleResults();
    if (!rows.length) return;

    try {
      const res = await fetch(`/api/export/${format}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ results: rows }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || "Export failed.");
      }
      const blob = await res.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `leads.${format}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(a.href);
    } catch (err) {
      showMessage(err.message);
    }
  }

  $("export-csv").addEventListener("click", () => exportAs("csv"));
  $("export-xlsx").addEventListener("click", () => exportAs("xlsx"));
})();
