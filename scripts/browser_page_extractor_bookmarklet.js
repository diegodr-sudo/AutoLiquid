(async () => {
  const startedAt = new Date().toISOString();
  const clean = (value) => String(value ?? "").replace(/\s+/g, " ").trim();
  const visible = (el) => {
    if (!el || !el.getBoundingClientRect) return false;
    const style = el.ownerDocument.defaultView.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
  };
  const fieldLabel = (el) => {
    const doc = el.ownerDocument;
    if (el.id) {
      const label = doc.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (label) return clean(label.textContent);
    }
    const wrapping = el.closest("label");
    if (wrapping) return clean(wrapping.textContent).replace(clean(el.value), "").trim();
    const row = el.closest("tr");
    if (row) {
      const cells = Array.from(row.children).map((cell) => clean(cell.textContent)).filter(Boolean);
      const idx = Array.from(row.children).findIndex((cell) => cell.contains(el));
      if (idx > 0) return cells[idx - 1] || "";
    }
    let previous = el.previousElementSibling;
    for (let i = 0; previous && i < 3; i += 1, previous = previous.previousElementSibling) {
      const text = clean(previous.textContent);
      if (text) return text.slice(0, 120);
    }
    return "";
  };
  const rectOf = (el) => {
    const rect = el.getBoundingClientRect();
    return {
      x: Math.round(rect.x),
      y: Math.round(rect.y),
      width: Math.round(rect.width),
      height: Math.round(rect.height),
    };
  };
  const collectDocument = (doc, path) => {
    const win = doc.defaultView;
    const fields = Array.from(doc.querySelectorAll("input, select, textarea")).map((el) => ({
      tag: el.tagName.toLowerCase(),
      type: el.getAttribute("type") || "",
      id: el.id || "",
      name: el.getAttribute("name") || "",
      label: fieldLabel(el),
      placeholder: el.getAttribute("placeholder") || "",
      value: el.tagName === "SELECT"
        ? Array.from(el.selectedOptions || []).map((opt) => clean(opt.textContent) || opt.value).join(" | ")
        : clean(el.value),
      checked: typeof el.checked === "boolean" ? el.checked : undefined,
      visible: visible(el),
      rect: rectOf(el),
    }));
    const buttons = Array.from(doc.querySelectorAll("button, input[type='button'], input[type='submit'], a[role='button']")).map((el) => ({
      tag: el.tagName.toLowerCase(),
      id: el.id || "",
      name: el.getAttribute("name") || "",
      text: clean(el.textContent || el.value || el.title || el.getAttribute("aria-label")),
      visible: visible(el),
      rect: rectOf(el),
    })).filter((item) => item.text || item.id || item.name);
    const links = Array.from(doc.querySelectorAll("a[href]")).map((el) => ({
      text: clean(el.textContent || el.title),
      href: el.href,
      id: el.id || "",
      visible: visible(el),
    })).filter((item) => item.text || item.href).slice(0, 300);
    const tables = Array.from(doc.querySelectorAll("table")).map((table, index) => ({
      index,
      id: table.id || "",
      caption: clean(table.caption?.textContent || ""),
      rows: Array.from(table.querySelectorAll("tr")).slice(0, 40).map((tr) =>
        Array.from(tr.children).map((cell) => clean(cell.textContent))
      ),
    }));
    const headings = Array.from(doc.querySelectorAll("h1,h2,h3,h4,[role='heading']")).map((el) => clean(el.textContent)).filter(Boolean);
    const forms = Array.from(doc.forms || []).map((form) => ({
      id: form.id || "",
      name: form.getAttribute("name") || "",
      action: form.action || "",
      method: form.method || "",
    }));
    return {
      path,
      url: win.location.href,
      title: doc.title,
      headings,
      forms,
      fields,
      buttons,
      links,
      tables,
    };
  };
  const documents = [collectDocument(document, "top")];
  Array.from(window.frames || []).forEach((frame, index) => {
    try {
      if (frame.document) documents.push(collectDocument(frame.document, `frame[${index}]`));
    } catch (error) {
      documents.push({ path: `frame[${index}]`, blocked: true, reason: String(error?.message || error) });
    }
  });
  const payload = {
    source: "AutoLiquid browser extractor",
    capturedAt: startedAt,
    userAgent: navigator.userAgent,
    page: { title: document.title, url: location.href },
    documents,
  };
  window.__AUTOLIQUID_PAGE_SNAPSHOT__ = payload;
  const text = JSON.stringify(payload, null, 2);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      const area = document.createElement("textarea");
      area.value = text;
      area.style.position = "fixed";
      area.style.left = "-9999px";
      document.body.appendChild(area);
      area.select();
      const ok = document.execCommand("copy");
      area.remove();
      return ok;
    }
  };
  const copied = await copy();
  document.getElementById("autoliquid-extractor-panel")?.remove();
  const panel = document.createElement("div");
  panel.id = "autoliquid-extractor-panel";
  panel.style.cssText = "position:fixed;right:16px;bottom:16px;z-index:2147483647;width:min(520px,calc(100vw - 32px));max-height:min(520px,calc(100vh - 32px));display:flex;flex-direction:column;gap:10px;padding:12px;border:1px solid #99f6e4;border-radius:14px;background:#f8fafc;color:#0f172a;box-shadow:0 24px 80px rgba(15,23,42,.28);font:12px system-ui,-apple-system,Segoe UI,sans-serif;";
  const summary = documents.map((doc) => `${doc.path}: ${doc.fields?.length || 0} campos, ${doc.tables?.length || 0} tabelas`).join(" | ");
  panel.innerHTML = `
    <div style="display:flex;align-items:center;justify-content:space-between;gap:8px">
      <strong style="font-size:13px">AutoLiquid: dados da pagina</strong>
      <button type="button" data-close style="border:1px solid #cbd5e1;border-radius:999px;background:white;padding:4px 8px;cursor:pointer">Fechar</button>
    </div>
    <div>${copied ? "JSON copiado para a area de transferencia." : "JSON gerado. Copia automatica bloqueada pelo navegador."}</div>
    <div style="color:#475569">${summary}</div>
    <textarea readonly style="width:100%;min-height:220px;resize:vertical;border:1px solid #cbd5e1;border-radius:10px;padding:8px;background:white;color:#0f172a;font:11px ui-monospace,SFMono-Regular,Menlo,monospace"></textarea>
  `;
  panel.querySelector("textarea").value = text;
  panel.querySelector("[data-close]").addEventListener("click", () => panel.remove());
  document.body.appendChild(panel);
})();
