// ==UserScript==
// @name         Study Question Bank Client Bridge
// @namespace    https://github.com/MelodyKnit/SmartAnswer
// @version      0.2.0
// @description  Bridge custom learning pages to StudyQuestionBankAssistant /ocs/query without modifying OCS itself.
// @author       StudyQuestionBankAssistant
// @match        *://*/*
// @run-at       document-idle
// @grant        GM_xmlhttpRequest
// @connect      127.0.0.1
// @connect      localhost
// @connect      ocs.classbot.top
// ==/UserScript==

(function () {
  "use strict";

  const STORAGE_KEY = "study_qb_client_bridge_config";
  const DEFAULT_CONFIG = {
    baseUrl: "http://127.0.0.1:8765",
    apiKey: "",
    autoAnswer: false,
  };
  const QUESTION_TYPE_MARKERS = [
    ["multiple", /(?:多选题|\[多选题\]|多项选择)/],
    ["judgement", /(?:判断题|\[判断题\]|判断正误|对错题)/],
    ["completion", /(?:填空题|\[填空题\]|简答题|问答题|论述题|心得|总结|作文)/],
    ["single", /(?:单选题|\[单选题\]|单项选择)/],
  ];
  const OPTION_LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("");
  const AUTO_ANSWER_DELAY_MS = 1400;
  const answeredQuestionKeys = new Set();
  let answerRunning = false;
  let autoAnswerTimer = 0;

  function loadConfig() {
    try {
      return { ...DEFAULT_CONFIG, ...JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}") };
    } catch (_error) {
      return { ...DEFAULT_CONFIG };
    }
  }

  function saveConfig(config) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
  }

  function normalizeText(value) {
    return String(value || "")
      .replace(/\u00a0/g, " ")
      .replace(/[ \t\r\n]+/g, " ")
      .trim();
  }

  function visible(element) {
    if (!(element instanceof Element)) {
      return false;
    }
    const style = window.getComputedStyle(element);
    if (style.display === "none" || style.visibility === "hidden" || style.opacity === "0") {
      return false;
    }
    const rect = element.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0 && rect.bottom >= 0 && rect.top <= window.innerHeight;
  }

  function inputUsable(input) {
    if (!(input instanceof HTMLInputElement) || input.disabled) {
      return false;
    }
    if (visible(input)) {
      return true;
    }
    const parent = input.closest("label,li,div,[role='radio'],[role='checkbox']");
    return Boolean(parent && visible(parent));
  }

  function detectPage() {
    const text = normalizeText(document.body.innerText).slice(0, 3000);
    return /四川外国语大学|智能练习|马克思主义|学习中心|答题卡/.test(text);
  }

  function detectQuestionType(text, root) {
    for (const [type, pattern] of QUESTION_TYPE_MARKERS) {
      if (pattern.test(text)) {
        return type;
      }
    }
    const inputs = Array.from(root.querySelectorAll("input")).filter(inputUsable);
    if (inputs.some((item) => item.type === "checkbox")) {
      return "multiple";
    }
    if (inputs.some((item) => item.type === "radio")) {
      return "single";
    }
    if (root.querySelector("textarea,input[type='text'],input:not([type])")) {
      return "completion";
    }
    return "single";
  }

  function parseOptions(lines) {
    const options = [];
    for (const line of lines) {
      const match = line.match(/^([A-Z])[\s.．、:：]+(.+)$/i);
      if (!match) {
        continue;
      }
      const label = match[1].toUpperCase();
      const text = normalizeText(match[2]);
      if (OPTION_LABELS.includes(label) && text && !placeholderOption(label, text)) {
        options.push(`${label}. ${text}`);
      }
    }
    return dedupe(options);
  }

  function placeholderOption(label, text) {
    const normalized = normalizeText(text).replace(/[.．、:：\s-]+/g, "").toUpperCase();
    return normalized === label.toUpperCase();
  }

  function extractTitle(lines, options) {
    const optionSet = new Set(options.map((item) => normalizeText(item)));
    const ignored = /^(查看解析|答题卡|正确|错误|部分正确|已做|未做|提交|上一题|下一题)$/;
    const useful = lines.filter((line) => {
      if (!line || ignored.test(line)) {
        return false;
      }
      if (/^[A-Z][\s.．、:：]+/.test(line)) {
        return false;
      }
      return !optionSet.has(line);
    });
    return normalizeText(useful.slice(0, 3).join(" "));
  }

  function dedupe(items) {
    const seen = new Set();
    const result = [];
    for (const item of items) {
      const key = normalizeText(item);
      if (!key || seen.has(key)) {
        continue;
      }
      seen.add(key);
      result.push(item);
    }
    return result;
  }

  function candidateRoots() {
    const roots = [];
    const seen = new Set();
    const selectors = [
      "[class*='question']",
      "[class*='Question']",
      "[class*='topic']",
      "[class*='Topic']",
      "[class*='exam']",
      "[class*='item']",
      ".el-card",
      "div",
      "li",
      "section",
      "article",
    ];
    for (const selector of selectors) {
      for (const element of document.querySelectorAll(selector)) {
        addCandidate(element, roots, seen);
      }
    }
    for (const input of document.querySelectorAll("input[type='radio'],input[type='checkbox']")) {
      let current = input.parentElement;
      for (let depth = 0; current && depth < 8; depth += 1) {
        addCandidate(current, roots, seen);
        current = current.parentElement;
      }
    }
    return roots;
  }

  function addCandidate(element, roots, seen) {
    if (!visible(element) || seen.has(element)) {
      return;
    }
    const text = normalizeText(element.innerText);
    if (text.length < 8 || text.length > 2500) {
      return;
    }
    const hasType = QUESTION_TYPE_MARKERS.some(([, pattern]) => pattern.test(text));
    const hasOptions = /(?:^|\s)[A-D][\s.．、:：]+/.test(text);
    const hasInput = Array.from(element.querySelectorAll("input,textarea")).some((input) => visible(input) || visible(input.closest("label,li,div")));
    if (!hasType && !hasOptions && !hasInput) {
      return;
    }
    seen.add(element);
    roots.push(element);
  }

  function extractQuestions() {
    const records = [];
    const seenTitles = new Set();
    for (const root of candidateRoots()) {
      const lines = normalizeText(root.innerText)
        .split(/(?=(?:[A-Z][\s.．、:：]))|\n/)
        .map(normalizeText)
        .filter(Boolean);
      const options = parseOptions(lines);
      const title = extractTitle(lines, options);
      if (!title || title.length < 6) {
        continue;
      }
      const key = normalizeText(title);
      if (seenTitles.has(key)) {
        continue;
      }
      seenTitles.add(key);
      const imageContext = extractImageContext(root);
      records.push({
        root,
        title,
        options,
        image_urls: imageContext.image_urls,
        option_image_urls: imageContext.option_image_urls,
        type: detectQuestionType(normalizeText(root.innerText), root),
        key: makeQuestionKey(title, options),
      });
    }
    return records;
  }

  function extractImageContext(root) {
    const image_urls = [];
    const option_image_urls = {};
    for (const image of root.querySelectorAll("img")) {
      if (!visible(image)) {
        continue;
      }
      const url = absoluteImageUrl(image);
      if (!url) {
        continue;
      }
      const label = optionLabelForImage(image);
      if (label && !option_image_urls[label]) {
        option_image_urls[label] = url;
      } else if (!image_urls.includes(url)) {
        image_urls.push(url);
      }
    }
    return { image_urls, option_image_urls };
  }

  function absoluteImageUrl(image) {
    const raw = image.currentSrc || image.src || image.getAttribute("data-src") || "";
    if (!raw || raw.startsWith("data:")) {
      return "";
    }
    try {
      const url = new URL(raw, window.location.href);
      return /^https?:$/.test(url.protocol) ? url.toString() : "";
    } catch (_error) {
      return "";
    }
  }

  function optionLabelForImage(image) {
    const container = image.closest("label,li,[role='radio'],[role='checkbox'],.el-radio,.el-checkbox,div");
    const text = normalizeText(container && (container.innerText || container.textContent));
    const match = text.match(/^([A-Z])[\s.．、:：]/i);
    return match ? match[1].toUpperCase() : "";
  }

  function makeQuestionKey(title, options) {
    return `${normalizeText(title)}::${options.map(normalizeText).join("|")}`;
  }

  function requestAnswer(question) {
    const config = loadConfig();
    const url = `${config.baseUrl.replace(/\/+$/, "")}/ocs/query`;
    const body = JSON.stringify({
      title: question.title,
      type: question.type,
      options: question.options,
      image_urls: question.image_urls,
      option_image_urls: question.option_image_urls || {},
    });
    const headers = {
      "Content-Type": "application/json",
      ...(config.apiKey ? { Authorization: `Bearer ${config.apiKey}` } : {}),
    };
    if (typeof GM_xmlhttpRequest !== "function") {
      return fetch(url, {
        method: "POST",
        headers,
        body,
        credentials: "omit",
      })
        .then((response) => response.json())
        .then((payload) => {
          if (payload.code !== 0) {
            throw new Error(payload.message || "query failed");
          }
          return payload.data || {};
        });
    }
    return new Promise((resolve, reject) => {
      GM_xmlhttpRequest({
        method: "POST",
        url,
        headers,
        data: body,
        timeout: 45000,
        onload: (response) => {
          try {
            const payload = JSON.parse(response.responseText || "{}");
            if (payload.code !== 0) {
              reject(new Error(payload.message || "query failed"));
              return;
            }
            resolve(payload.data || {});
          } catch (error) {
            reject(error);
          }
        },
        onerror: () => reject(new Error("request failed")),
        ontimeout: () => reject(new Error("request timeout")),
      });
    });
  }

  function answerLabels(answer) {
    const text = normalizeText(answer).toUpperCase();
    if (!text) {
      return [];
    }
    const normalized = text.replace(/[\[\]"'，,、\s]+/g, "#").replace(/#+/g, "#");
    const parts = normalized.includes("#") ? normalized.split("#") : text.split("");
    return dedupe(parts.map((item) => item.replace(/[^A-Z]/g, "")).filter(Boolean));
  }

  function fillQuestion(question, data) {
    const answer = data.answer || data.answer_text || "";
    if (!answer) {
      markQuestion(question.root, "未返回答案", "warn");
      return false;
    }
    if (question.type === "completion") {
      return fillTextAnswer(question.root, data.answer_text || answer);
    }
    if (question.type === "judgement") {
      return clickJudgement(question.root, answer);
    }
    const labels = answerLabels(answer);
    let clicked = 0;
    for (const label of labels) {
      clicked += clickOptionByLabel(question.root, label) ? 1 : 0;
    }
    markQuestion(question.root, clicked ? `已回填 ${answer}` : `未找到选项 ${answer}`, clicked ? "ok" : "warn");
    return clicked > 0;
  }

  function fillTextAnswer(root, answer) {
    const field = Array.from(root.querySelectorAll("textarea,input[type='text'],input:not([type])")).find(visible);
    if (!field) {
      markQuestion(root, "未找到输入框", "warn");
      return false;
    }
    field.focus();
    field.value = answer;
    dispatchInputEvents(field);
    markQuestion(root, "已回填文本", "ok");
    return true;
  }

  function clickJudgement(root, answer) {
    const text = normalizeText(answer);
    const wanted = /^(A|对|正确|TRUE|YES)$/i.test(text) ? ["对", "正确", "A"] : ["错", "错误", "B"];
    for (const item of wanted) {
      if (clickOptionByText(root, item)) {
        markQuestion(root, `已回填 ${item}`, "ok");
        return true;
      }
    }
    markQuestion(root, `未找到判断项 ${answer}`, "warn");
    return false;
  }

  function clickOptionByLabel(root, label) {
    const index = OPTION_LABELS.indexOf(label.toUpperCase());
    const inputs = Array.from(root.querySelectorAll("input[type='radio'],input[type='checkbox']")).filter(inputUsable);
    if (index >= 0 && inputs[index]) {
      smartClick(clickTargetForInput(inputs[index]));
      return true;
    }
    return clickOptionByText(root, `${label}.`) || clickOptionByText(root, `${label}．`) || clickOptionByText(root, `${label}、`);
  }

  function clickOptionByText(root, text) {
    const target = Array.from(root.querySelectorAll("label,li,div,span,p")).find((element) => {
      if (!visible(element)) {
        return false;
      }
      const content = normalizeText(element.innerText || element.textContent);
      return content === text || content.startsWith(text);
    });
    if (!target) {
      return false;
    }
    const clickable = target.closest("label,li,[role='radio'],[role='checkbox'],.el-radio,.el-checkbox,div") || target;
    smartClick(clickable);
    return true;
  }

  function clickTargetForInput(input) {
    const labelByFor = input.id ? document.querySelector(`label[for="${CSS.escape(input.id)}"]`) : null;
    return labelByFor || input.closest("label,li,[role='radio'],[role='checkbox'],.el-radio,.el-checkbox,div") || input;
  }

  function smartClick(element) {
    element.scrollIntoView({ block: "center", inline: "center" });
    element.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
    element.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
    element.click();
    element.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
    element.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function dispatchInputEvents(element) {
    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
    element.dispatchEvent(new Event("blur", { bubbles: true }));
  }

  function markQuestion(root, message, level) {
    let badge = root.querySelector(":scope > .study-qb-bridge-badge");
    if (!badge) {
      badge = document.createElement("div");
      badge.className = "study-qb-bridge-badge";
      root.prepend(badge);
    }
    badge.textContent = message;
    badge.dataset.level = level;
  }

  function createPanel() {
    if (document.getElementById("study-qb-bridge-panel")) {
      return;
    }
    const panel = document.createElement("div");
    panel.id = "study-qb-bridge-panel";
    panel.innerHTML = `
      <div class="study-qb-bridge-title">题库桥接</div>
      <div class="study-qb-bridge-row">
        <input data-role="base-url" placeholder="服务地址" />
      </div>
      <div class="study-qb-bridge-row">
        <input data-role="api-key" placeholder="API Key，可留空" type="password" />
      </div>
      <div class="study-qb-bridge-actions">
        <button type="button" data-role="scan">识别题目</button>
        <button type="button" data-role="answer">答当前页</button>
      </div>
      <label class="study-qb-bridge-toggle">
        <input data-role="auto-answer" type="checkbox" />
        自动答当前页
      </label>
      <div class="study-qb-bridge-status" data-role="status">等待操作</div>
    `;
    document.documentElement.appendChild(panel);

    const config = loadConfig();
    panel.querySelector("[data-role='base-url']").value = config.baseUrl;
    panel.querySelector("[data-role='api-key']").value = config.apiKey;
    panel.querySelector("[data-role='auto-answer']").checked = config.autoAnswer === true;
    panel.querySelector("[data-role='base-url']").addEventListener("change", persistPanelConfig);
    panel.querySelector("[data-role='api-key']").addEventListener("change", persistPanelConfig);
    panel.querySelector("[data-role='auto-answer']").addEventListener("change", () => {
      persistPanelConfig();
      scheduleAutoAnswer("toggle");
    });
    panel.querySelector("[data-role='scan']").addEventListener("click", scanVisibleQuestions);
    panel.querySelector("[data-role='answer']").addEventListener("click", () => answerVisibleQuestions({ force: true }));
  }

  function persistPanelConfig() {
    const panel = document.getElementById("study-qb-bridge-panel");
    saveConfig({
      baseUrl: panel.querySelector("[data-role='base-url']").value.trim() || DEFAULT_CONFIG.baseUrl,
      apiKey: panel.querySelector("[data-role='api-key']").value.trim(),
      autoAnswer: panel.querySelector("[data-role='auto-answer']").checked,
    });
  }

  function setStatus(message) {
    const panel = document.getElementById("study-qb-bridge-panel");
    const status = panel && panel.querySelector("[data-role='status']");
    if (status) {
      status.textContent = message;
    }
  }

  function scanVisibleQuestions() {
    persistPanelConfig();
    const questions = extractQuestions();
    for (const question of questions) {
      markQuestion(question.root, `${question.type} / ${question.options.length} 个选项`, "info");
    }
    setStatus(`识别到 ${questions.length} 道可见题`);
  }

  async function answerVisibleQuestions(options = {}) {
    persistPanelConfig();
    if (answerRunning) {
      setStatus("已有答题任务运行中");
      return;
    }
    const questions = extractQuestions().filter((question) => options.force || !answeredQuestionKeys.has(question.key));
    if (!questions.length) {
      setStatus(options.force ? "未识别到可见题" : "当前可见题已处理");
      return;
    }
    let ok = 0;
    answerRunning = true;
    setStatus(`开始查询 ${questions.length} 道题`);
    try {
      for (let index = 0; index < questions.length; index += 1) {
        const question = questions[index];
        try {
          markQuestion(question.root, "查询中", "info");
          const data = await requestAnswer(question);
          answeredQuestionKeys.add(question.key);
          if (fillQuestion(question, data)) {
            ok += 1;
          }
        } catch (error) {
          markQuestion(question.root, error.message || "查询失败", "warn");
          answeredQuestionKeys.add(question.key);
        }
        setStatus(`已处理 ${index + 1}/${questions.length}，成功 ${ok}`);
      }
    } finally {
      answerRunning = false;
    }
  }

  function scheduleAutoAnswer(reason) {
    const config = loadConfig();
    if (config.autoAnswer === false || !detectPage()) {
      return;
    }
    window.clearTimeout(autoAnswerTimer);
    autoAnswerTimer = window.setTimeout(() => {
      const questions = extractQuestions();
      if (!questions.length) {
        setStatus("未识别到可见题");
        return;
      }
      setStatus(`自动检测到 ${questions.length} 道题，准备答题`);
      answerVisibleQuestions({ reason });
    }, AUTO_ANSWER_DELAY_MS);
  }

  function observeQuestionChanges() {
    const observer = new MutationObserver(() => scheduleAutoAnswer("dom-change"));
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
    });
    window.addEventListener("hashchange", () => scheduleAutoAnswer("route-change"));
    window.addEventListener("popstate", () => scheduleAutoAnswer("route-change"));
  }

  function installStyles() {
    const style = document.createElement("style");
    style.textContent = `
      #study-qb-bridge-panel {
        position: fixed;
        right: 18px;
        bottom: 18px;
        z-index: 2147483647;
        width: 260px;
        padding: 12px;
        border: 1px solid rgba(37, 99, 235, 0.24);
        border-radius: 8px;
        background: rgba(255, 255, 255, 0.96);
        box-shadow: 0 12px 32px rgba(15, 23, 42, 0.18);
        color: #0f172a;
        font-size: 13px;
        line-height: 1.4;
      }
      #study-qb-bridge-panel input {
        box-sizing: border-box;
        width: 100%;
        height: 30px;
        margin-top: 8px;
        padding: 4px 8px;
        border: 1px solid #cbd5e1;
        border-radius: 6px;
        font: inherit;
      }
      .study-qb-bridge-title {
        font-weight: 700;
      }
      .study-qb-bridge-actions {
        display: flex;
        gap: 8px;
        margin-top: 10px;
      }
      .study-qb-bridge-actions button {
        flex: 1;
        height: 30px;
        border: 0;
        border-radius: 6px;
        background: #2563eb;
        color: #fff;
        cursor: pointer;
        font: inherit;
      }
      .study-qb-bridge-toggle {
        display: flex;
        align-items: center;
        gap: 6px;
        margin-top: 9px;
        color: #334155;
        user-select: none;
      }
      .study-qb-bridge-toggle input {
        width: 14px !important;
        height: 14px !important;
        margin: 0 !important;
      }
      .study-qb-bridge-status {
        margin-top: 8px;
        color: #475569;
      }
      .study-qb-bridge-badge {
        display: inline-flex;
        align-items: center;
        min-height: 22px;
        margin: 6px 0;
        padding: 2px 8px;
        border-radius: 999px;
        background: #e0f2fe;
        color: #0369a1;
        font-size: 12px;
        font-weight: 600;
      }
      .study-qb-bridge-badge[data-level="ok"] {
        background: #dcfce7;
        color: #15803d;
      }
      .study-qb-bridge-badge[data-level="warn"] {
        background: #fee2e2;
        color: #b91c1c;
      }
    `;
    document.documentElement.appendChild(style);
  }

  function boot() {
    if (!document.body || !detectPage()) {
      return;
    }
    installStyles();
    createPanel();
    observeQuestionChanges();
    scheduleAutoAnswer("boot");
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
