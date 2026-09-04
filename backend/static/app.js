(function () {
  const input = document.getElementById("raw-input");
  const sendBtn = document.getElementById("send-btn");
  const micBtn = document.getElementById("mic-btn");
  const plusBtn = document.getElementById("plus-btn");
  const inputPanel = document.getElementById("input-panel");
  const attachmentTray = document.getElementById("attachment-tray");
  const uploadMenu = document.getElementById("upload-menu");
  const uploadMenuBackdrop = document.getElementById("upload-menu-backdrop");
  const fileInput = document.getElementById("file-input");
  const uploadStatus = document.getElementById("upload-status");
  const dropOverlay = document.getElementById("drop-overlay");
  const modeBtn = document.getElementById("mode-btn");
  const modeLabel = document.getElementById("mode-label");
  const modeMenu = document.getElementById("mode-menu");
  const menuBtn = document.getElementById("menu-btn");
  const drawerClose = document.getElementById("drawer-close");
  const drawer = document.getElementById("drawer");
  const overlay = document.getElementById("overlay");
  const hero = document.getElementById("hero");
  const heroSub = hero.querySelector(".hero-sub");
  const messages = document.getElementById("messages");
  const result = document.getElementById("result");
  const history = document.getElementById("history");
  const newBtn = document.getElementById("new-btn");
  const toastEl = document.getElementById("toast");
  const weekLabel = document.getElementById("week-label");
  const heroWeekRange = document.getElementById("hero-week-range");
  const heroOutputName = document.getElementById("hero-output-name");
  const drawerBack = document.getElementById("drawer-back");
  const drawerTitle = document.getElementById("drawer-title");
  const drawerMainView = document.getElementById("drawer-main-view");
  const drawerSettingsView = document.getElementById("drawer-settings-view");
  const drawerHelpView = document.getElementById("drawer-help-view");
  const settingsBtn = document.getElementById("settings-btn");
  const helpBtn = document.getElementById("help-btn");
  const historyRefresh = document.getElementById("history-refresh");
  const settingsForm = document.getElementById("settings-form");
  const settingsIntro = document.getElementById("settings-intro");
  const settingsError = document.getElementById("settings-error");
  const settingsSave = document.getElementById("settings-save");
  const weekOneInput = document.getElementById("week-one-input");
  const weekOneNote = document.getElementById("week-one-note");
  const detailSelect = document.getElementById("settings-detail-level");
  const toneSelect = document.getElementById("settings-tone");
  const privacySummary = document.getElementById("privacy-summary");
  const deleteDataBtn = document.getElementById("delete-data-btn");
  const weeklyTemplateBtn = document.getElementById("weekly-template-btn");
  const savedTemplateNav = document.getElementById("saved-template-nav");
  const customTemplateBtn = document.getElementById("custom-template-btn");
  const legacyTemplateDrafts = document.getElementById("legacy-template-drafts");
  const templateWorkspace = document.getElementById("template-workspace");
  const templateWorkspaceBack = document.getElementById("template-workspace-back");
  const templateWorkspaceTitle = document.getElementById("template-workspace-title");
  const templateSaveBtn = document.getElementById("template-save-btn");
  const templateStart = document.getElementById("template-start");
  const templateManualBtn = document.getElementById("template-manual-btn");
  const templateLearnBtn = document.getElementById("template-learn-btn");
  const templateLearn = document.getElementById("template-learn");
  const templateLearnDrop = document.getElementById("template-learn-drop");
  const templateFileBtn = document.getElementById("template-file-btn");
  const templateFileInput = document.getElementById("template-file-input");
  const templateSampleList = document.getElementById("template-sample-list");
  const templateLearnResult = document.getElementById("template-learn-result");
  const templateAnalyzeBtn = document.getElementById("template-analyze-btn");
  const templateLearnCancel = document.getElementById("template-learn-cancel");
  const templateEditor = document.getElementById("template-editor");
  const templateEditorPane = document.getElementById("template-editor-pane");
  const templatePreviewPane = document.getElementById("template-preview-pane");
  const templateTitlePattern = document.getElementById("template-title-pattern");
  const templateSectionsEditor = document.getElementById("template-sections-editor");
  const templateAddSection = document.getElementById("template-add-section");
  const templatePreview = document.getElementById("template-preview");
  const templateAiInput = document.getElementById("template-ai-input");
  const templateAiSend = document.getElementById("template-ai-send");
  const templateAiMessages = document.getElementById("template-ai-messages");
  const templateNameDialog = document.getElementById("template-name-dialog");
  const templateNameForm = document.getElementById("template-name-form");
  const templateNameInput = document.getElementById("template-name-input");
  const templateNameError = document.getElementById("template-name-error");
  const templateNameCancel = document.getElementById("template-name-cancel");
  const quotaDialogBackdrop = document.getElementById("quota-dialog-backdrop");
  const quotaDialog = document.getElementById("quota-dialog");
  const quotaDialogDescription = document.getElementById("quota-dialog-description");
  const quotaDialogClose = document.getElementById("quota-dialog-close");

  let sessionId = newSessionId();
  let currentWeekId = null;
  let isStreaming = false;
  let toastTimer = null;
  let settingsState = null;
  let settingsDraft = null;
  let settingsLoaded = false;
  let settingsSaving = false;
  let drawerView = "main";
  let drawerReturnFocus = null;
  let currentSessionDirty = false;
  let selectedAttachments = [];
  const sentAttachmentPreviewUrls = new Set();
  let dragDepth = 0;
  let chatMode = "advanced";
  let quotaDialogReturnFocus = null;
  let templatesState = { templates: [], drafts: [], selected_template_id: null };
  let activeTemplateId = null;
  let templateDraft = null;
  let templateSamples = [];
  let templateUploadSessionId = newSessionId();
  let templateBusy = false;
  let templateDraftDirty = false;
  let templatePersistTimer = null;
  let templatePersistInFlight = null;
  let templateDraftEditVersion = 0;
  let templateNameSaving = false;

  const MAX_ATTACHMENT_SIZE = 16 * 1024 * 1024;
  const MAX_ATTACHMENTS = 12;
  const SUPPORTED_FILE_PATTERN =
    /\.(docx|pptx|pdf|txt|md|markdown|csv|tsv|xlsx|json|jsonl|ya?ml|xml|html?|css|jsx?|tsx?|py|java|c|h|cpp|hpp|go|rs|sql|sh|log|ini|toml|conf|png|jpe?g|webp|bmp|tiff?|zip)$/i;

  const DOWNLOAD_ICON =
    '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v12M6 12l6 6 6-6M4 20h16"/></svg>';

  function newSessionId() {
    return window.crypto && window.crypto.randomUUID
      ? window.crypto.randomUUID()
      : "s-" + Date.now() + "-" + Math.random().toString(16).slice(2);
  }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function escAttr(s) {
    return esc(s).replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function toast(msg) {
    toastEl.textContent = msg;
    toastEl.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      toastEl.hidden = true;
    }, 2600);
  }

  function quotaResetLabel(value) {
    const timestamp = Number(value);
    if (!Number.isFinite(timestamp) || timestamp <= 0) return "";
    const reset = new Date(timestamp * 1000);
    if (Number.isNaN(reset.getTime())) return "";
    return (
      reset.getMonth() +
      1 +
      " 月 " +
      reset.getDate() +
      " 日 " +
      String(reset.getHours()).padStart(2, "0") +
      ":" +
      String(reset.getMinutes()).padStart(2, "0")
    );
  }

  function showQuotaDialog(res, detail) {
    const parsedLimit = Number.parseInt(res.headers.get("X-RateLimit-Limit") || "", 10);
    const limit = Number.isFinite(parsedLimit) && parsedLimit > 0 ? parsedLimit : 10;
    const resetLabel = quotaResetLabel(res.headers.get("X-RateLimit-Reset"));
    quotaDialogDescription.textContent = resetLabel
      ? "每天最多可发送 " + limit + " 条消息，额度将于 " + resetLabel + " 恢复。"
      : detail || "每天最多可发送 " + limit + " 条消息，请明天再来。";
    quotaDialogReturnFocus = input;
    quotaDialogBackdrop.hidden = false;
    document.body.classList.add("quota-dialog-open");
    window.requestAnimationFrame(function () {
      quotaDialogClose.focus();
    });
  }

  function closeQuotaDialog() {
    if (quotaDialogBackdrop.hidden) return;
    quotaDialogBackdrop.hidden = true;
    document.body.classList.remove("quota-dialog-open");
    const target = quotaDialogReturnFocus;
    quotaDialogReturnFocus = null;
    if (target && target.focus) target.focus();
  }

  function formatBytes(value) {
    if (value < 1024) return value + " B";
    if (value < 1024 * 1024) return (value / 1024).toFixed(value < 10240 ? 1 : 0) + " KB";
    return (value / (1024 * 1024)).toFixed(1) + " MB";
  }

  function attachmentExtension(item) {
    const match = /\.([^.]+)$/.exec(String((item && item.name) || ""));
    return match ? match[1].toUpperCase() : "文件";
  }

  function isImageAttachment(item) {
    const contentType = String(
      (item && (item.content_type || item.contentType)) || ""
    ).toLowerCase();
    return Boolean(
      item &&
      (item.category === "图片" ||
        contentType.indexOf("image/") === 0 ||
        /\.(png|jpe?g|webp|bmp|tiff?)$/i.test(item.name || ""))
    );
  }

  function attachmentKind(item) {
    const extension = attachmentExtension(item);
    if (isImageAttachment(item)) return { label: "图片", className: "image" };
    if (item.category === "数据表格" || /^(CSV|TSV|XLSX)$/.test(extension))
      return { label: "表格", className: "data" };
    if (item.category === "压缩包" || extension === "ZIP")
      return { label: "压缩包", className: "zip" };
    return { label: "文档", className: "doc" };
  }

  function createAttachmentIcon(className, kind) {
    const icon = document.createElement("span");
    icon.className = className + " " + kind.className;
    icon.setAttribute("aria-hidden", "true");
    const glyph = document.createElement("span");
    glyph.className = "attachment-glyph";
    icon.appendChild(glyph);
    return icon;
  }

  function revokeAttachmentPreview(item) {
    if (!item || !item.previewUrl || !window.URL || !window.URL.revokeObjectURL) return;
    window.URL.revokeObjectURL(item.previewUrl);
    sentAttachmentPreviewUrls.delete(item.previewUrl);
    item.previewUrl = "";
  }

  function releaseSentAttachmentPreviews() {
    if (!window.URL || !window.URL.revokeObjectURL) return;
    sentAttachmentPreviewUrls.forEach(function (url) {
      window.URL.revokeObjectURL(url);
    });
    sentAttachmentPreviewUrls.clear();
  }

  function sentAttachmentMeta(item) {
    const extension = attachmentExtension(item);
    const label =
      item.category === "压缩包"
        ? "压缩包"
        : isImageAttachment(item)
          ? "图片"
          : item.category === "数据表格"
            ? "表格"
            : "文件";
    return extension + " " + label + " · " + formatBytes(Number(item.size) || 0);
  }

  function renderAttachments() {
    attachmentTray.innerHTML = "";
    attachmentTray.hidden = selectedAttachments.length === 0;
    document.body.classList.toggle("composer-has-attachments", selectedAttachments.length > 0);
    selectedAttachments.forEach(function (item) {
      const card = document.createElement("div");
      card.className = "attachment-item " + item.status;
      const kind = attachmentKind(item);
      const icon = createAttachmentIcon("attachment-icon", kind);
      if (kind.className === "image" && item.previewUrl) {
        const thumb = document.createElement("img");
        thumb.className = "attachment-thumb";
        thumb.src = item.previewUrl;
        thumb.alt = "";
        icon.appendChild(thumb);
      }
      const copy = document.createElement("span");
      copy.className = "attachment-copy";
      const name = document.createElement("strong");
      name.textContent = item.name;
      name.title = item.name;
      const meta = document.createElement("small");
      if (item.status === "uploading") meta.textContent = "正在读取 · " + formatBytes(item.size);
      else if (item.status === "error") meta.textContent = item.error || "读取失败";
      else meta.textContent = item.summary + (item.truncated ? " · 已截取" : "");
      copy.appendChild(name);
      copy.appendChild(meta);
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "attachment-remove";
      remove.setAttribute("aria-label", "移除 " + item.name);
      remove.textContent = "×";
      remove.addEventListener("click", function () {
        removeAttachment(item.localId);
      });
      card.appendChild(icon);
      card.appendChild(copy);
      card.appendChild(remove);
      attachmentTray.appendChild(card);
    });
    syncSend();
  }

  function closeUploadMenu() {
    uploadMenu.hidden = true;
    uploadMenuBackdrop.hidden = true;
    plusBtn.setAttribute("aria-expanded", "false");
    document.body.classList.remove("upload-menu-open");
  }

  function openUploadMenu() {
    if (!(settingsState && settingsState.configured)) {
      openStartupSetup();
      return;
    }
    if (isStreaming || isRecording) return;
    const willOpen = uploadMenu.hidden;
    closeModeMenu();
    if (!willOpen) {
      closeUploadMenu();
      return;
    }
    uploadMenu.hidden = false;
    uploadMenuBackdrop.hidden = false;
    plusBtn.setAttribute("aria-expanded", "true");
    document.body.classList.add("upload-menu-open");
    const first = uploadMenu.querySelector("[data-upload-accept]");
    if (first && window.matchMedia("(min-width: 621px)").matches) first.focus();
  }

  async function removeAttachment(localId) {
    const item = selectedAttachments.find(function (entry) {
      return entry.localId === localId;
    });
    selectedAttachments = selectedAttachments.filter(function (entry) {
      return entry.localId !== localId;
    });
    revokeAttachmentPreview(item);
    renderAttachments();
    if (item && item.id) {
      try {
        await fetch(
          "api/attachments/" +
            encodeURIComponent(item.id) +
            "?session_id=" +
            encodeURIComponent(sessionId),
          { method: "DELETE" }
        );
      } catch (e) {}
    }
  }

  async function uploadFile(file) {
    if (!file || !file.name) return;
    if (selectedAttachments.length >= MAX_ATTACHMENTS) {
      toast("一次最多添加 " + MAX_ATTACHMENTS + " 个附件");
      return;
    }
    if (file.size > MAX_ATTACHMENT_SIZE) {
      toast(file.name + " 超过 16MB，未添加");
      return;
    }
    if (!SUPPORTED_FILE_PATTERN.test(file.name)) {
      toast(file.name + " 的格式暂不支持");
      return;
    }
    const item = {
      localId: "upload-" + Date.now() + "-" + Math.random().toString(16).slice(2),
      name: file.name,
      size: file.size,
      status: "uploading",
      category: "",
      contentType: file.type || "",
      previewUrl:
        isImageAttachment({ name: file.name, contentType: file.type }) &&
        window.URL &&
        window.URL.createObjectURL
          ? window.URL.createObjectURL(file)
          : "",
    };
    selectedAttachments.push(item);
    uploadStatus.textContent = "正在读取 " + file.name;
    renderAttachments();
    const body = new FormData();
    body.append("session_id", sessionId);
    body.append("file", file, file.name);
    try {
      const res = await fetch("api/attachments", { method: "POST", body: body });
      if (!res.ok) throw new Error(await readErrorDetail(res, "附件读取失败"));
      const data = await res.json();
      if (
        !selectedAttachments.some(function (entry) {
          return entry.localId === item.localId;
        })
      ) {
        fetch(
          "api/attachments/" +
            encodeURIComponent(data.id) +
            "?session_id=" +
            encodeURIComponent(sessionId),
          { method: "DELETE" }
        ).catch(function () {});
        return;
      }
      Object.assign(item, data, { status: "ready" });
      uploadStatus.textContent = file.name + " 已读取完成";
    } catch (e) {
      item.status = "error";
      item.error = e.message;
      uploadStatus.textContent = file.name + " 读取失败：" + e.message;
    } finally {
      renderAttachments();
    }
  }

  function handleFiles(files) {
    closeUploadMenu();
    Array.from(files || []).forEach(function (file) {
      uploadFile(file);
    });
  }

  function clearAttachments(deleteRemote) {
    const previous = selectedAttachments.slice();
    selectedAttachments = [];
    renderAttachments();
    if (!deleteRemote) return;
    previous.forEach(function (item) {
      revokeAttachmentPreview(item);
      if (!item.id) return;
      fetch(
        "api/attachments/" +
          encodeURIComponent(item.id) +
          "?session_id=" +
          encodeURIComponent(sessionId),
        { method: "DELETE" }
      ).catch(function () {});
    });
  }

  function autoGrow() {
    const singleLineHeight = 25;

    // 始终先按紧凑布局测量：只有文字确实超过左右功能区之间的
    // 单行宽度时才切换到大框，删除文字后也能自动恢复。
    inputPanel.classList.remove("expanded");
    input.style.height = singleLineHeight + "px";
    const needsExpanded =
      input.value.length > 0 &&
      (input.value.indexOf("\n") !== -1 || input.scrollHeight > singleLineHeight + 2);

    inputPanel.classList.toggle("expanded", needsExpanded);
    document.body.classList.toggle("composer-expanded", needsExpanded);

    if (needsExpanded) {
      input.style.height = "auto";
      input.style.height = Math.min(input.scrollHeight, 75) + "px";
    }
  }

  function syncSend() {
    const hasText = input.value.trim().length > 0;
    const hasReadyAttachments = selectedAttachments.some(function (item) {
      return item.status === "ready";
    });
    const hasPendingAttachments = selectedAttachments.some(function (item) {
      return item.status === "uploading";
    });
    const hasContent = hasText || hasReadyAttachments;
    const canCompose = Boolean(settingsLoaded && settingsState && settingsState.configured);
    inputPanel.classList.toggle("has-text", hasContent);
    sendBtn.disabled = isStreaming || hasPendingAttachments || !hasContent || !canCompose;
    micBtn.disabled = isStreaming || !canCompose;
    plusBtn.disabled = isStreaming || !canCompose;
    input.disabled = !canCompose;
  }

  function cloneSettings(value) {
    return JSON.parse(JSON.stringify(value || {}));
  }

  function pad2(num) {
    return String(num).padStart(2, "0");
  }

  function parseDateInput(value) {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value || ""));
    if (!match) return null;
    return new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  }

  function toIsoDate(date) {
    return [date.getFullYear(), pad2(date.getMonth() + 1), pad2(date.getDate())].join("-");
  }

  function mondayFromValue(value) {
    const date = parseDateInput(value);
    if (!date) return "";
    const day = date.getDay();
    date.setDate(date.getDate() + (day === 0 ? -6 : 1 - day));
    return toIsoDate(date);
  }

  function addDays(value, days) {
    const date = parseDateInput(value);
    if (!date) return "";
    date.setDate(date.getDate() + days);
    return toIsoDate(date);
  }

  function currentMondayIso() {
    const date = new Date();
    const day = date.getDay();
    date.setDate(date.getDate() + (day === 0 ? -6 : 1 - day));
    return toIsoDate(date);
  }

  function formatDate(value) {
    const date = parseDateInput(value);
    if (!date) return "";
    return date.getFullYear() + "." + pad2(date.getMonth() + 1) + "." + pad2(date.getDate());
  }

  function formatRange(start) {
    return formatDate(start) + "–" + formatDate(addDays(start, 6));
  }

  function weekNumberFromFirst(firstStart) {
    const current = parseDateInput(currentMondayIso());
    const first = parseDateInput(firstStart);
    if (!current || !first) return 1;
    return Math.floor(Math.round((current - first) / 86400000) / 7) + 1;
  }

  function currentWeekLabel(data, firstStart) {
    if (firstStart) {
      return "第 " + weekNumberFromFirst(firstStart) + " 周";
    }
    if (data && data.current_week && data.current_week.display_label) {
      return data.current_week.display_label;
    }
    return "第 " + weekNumberFromFirst(currentMondayIso()) + " 周";
  }

  function updateTopWeekInfo(data) {
    const week = data && data.current_week;
    const label = currentWeekLabel(data, settingsDraft && settingsDraft.week_one_start);
    weekLabel.textContent = label;
    if (heroWeekRange) {
      heroWeekRange.textContent =
        week && week.week_start && week.week_end
          ? "本周 " + formatRange(week.week_start)
          : "本周 " + formatRange(currentMondayIso());
    }
  }

  async function readErrorDetail(res, fallback) {
    try {
      const data = await res.json();
      return data && data.detail ? data.detail : fallback;
    } catch (e) {
      return fallback;
    }
  }

  function parseSseBlock(block) {
    const data = String(block || "")
      .split(/\r?\n/)
      .filter(function (line) {
        return line.indexOf("data:") === 0;
      })
      .map(function (line) {
        return line.slice(5).replace(/^ /, "");
      })
      .join("\n");
    if (!data) return null;
    try {
      return JSON.parse(data);
    } catch (e) {
      return null;
    }
  }

  function consumeSseBuffer(buffer, onEvent, flush) {
    const boundary = /\r?\n\r?\n/;
    let match;
    while ((match = boundary.exec(buffer)) !== null) {
      const event = parseSseBlock(buffer.slice(0, match.index));
      buffer = buffer.slice(match.index + match[0].length);
      if (event) onEvent(event);
    }
    if (flush && buffer.trim()) {
      const event = parseSseBlock(buffer);
      if (event) onEvent(event);
      return "";
    }
    return buffer;
  }

  function setSettingsError(message) {
    settingsError.textContent = message || "";
    settingsError.hidden = !message;
  }

  function fillSettingsForm() {
    const values = settingsDraft || {};
    weekOneInput.value = values.week_one_start || "";
    const constraints = (settingsState && settingsState.constraints) || {};
    weekOneInput.max = constraints.latest_week_one_end || constraints.latest_week_one_start || "";
    weekOneNote.textContent =
      settingsState && settingsState.configured
        ? "修改后历史记录会按新的第 1 周重新编号。"
        : "首次设置完成后即可开始记录。每周按周一至周日计算。";
    detailSelect.value = values.detail_level || "standard";
    toneSelect.value = values.tone || "natural";
    settingsIntro.textContent =
      settingsState && settingsState.configured
        ? "这些设置会影响周次标题和 AI 整理方式。保存后将开始新会话。"
        : "完成首次设置后即可开始记录。";
    setSettingsError("");
  }

  function setDrawerView(view, shouldFocus) {
    drawerView = view;
    drawerMainView.hidden = view !== "main";
    drawerSettingsView.hidden = view !== "settings";
    drawerHelpView.hidden = view !== "help";
    drawerBack.hidden = view === "main" || !(settingsState && settingsState.configured);
    drawerClose.disabled = !(settingsState && settingsState.configured);
    drawerTitle.textContent =
      view === "settings" ? "设置" : view === "help" ? "使用帮助" : "快捷菜单";
    if (view === "settings") {
      settingsDraft = cloneSettings(
        (settingsState && settingsState.settings) || (settingsState && settingsState.defaults) || {}
      );
      fillSettingsForm();
    }
    if (shouldFocus !== false) {
      window.requestAnimationFrame(function () {
        const target = view === "settings" ? weekOneInput : view === "help" ? drawerBack : newBtn;
        if (target) target.focus();
      });
    }
  }

  async function loadSettings() {
    try {
      const res = await fetch("api/settings");
      if (!res.ok) {
        throw new Error(await readErrorDetail(res, "设置加载失败"));
      }
      const data = await res.json();
      settingsState = data;
      settingsDraft = cloneSettings(data.settings || data.defaults || {});
      settingsLoaded = true;
      updateTopWeekInfo(data);
      document.body.classList.remove("booting");
      if (data.configured) {
        showHero();
        syncSend();
        loadHistory();
        loadTemplates();
      } else {
        reset();
        openDrawer("settings");
      }
    } catch (e) {
      document.body.classList.remove("booting");
      toast("设置加载失败：" + e.message);
      settingsState = {
        configured: false,
        settings: {
          week_one_start: currentMondayIso(),
          purpose_mode: "default",
          custom_purpose_name: "",
          custom_purpose_description: "",
          detail_level: "standard",
          tone: "natural",
        },
        defaults: {
          week_one_start: currentMondayIso(),
          purpose_mode: "default",
          custom_purpose_name: "",
          custom_purpose_description: "",
          detail_level: "standard",
          tone: "natural",
        },
        constraints: { latest_week_one_end: "" },
        current_week: {
          week_number: 1,
          week_start: currentMondayIso(),
          week_end: addDays(currentMondayIso(), 6),
          display_label: "第 1 周",
        },
      };
      settingsDraft = cloneSettings(settingsState.defaults);
      settingsLoaded = true;
      updateTopWeekInfo(settingsState);
      reset();
      openDrawer("settings");
    }
  }

  async function saveSettings() {
    if (settingsSaving) return;
    setSettingsError("");
    const alignedWeek = mondayFromValue(weekOneInput.value);
    const payload = {
      week_one_start: alignedWeek,
      purpose_mode: "default",
      custom_purpose_name: "",
      custom_purpose_description: "",
      detail_level: detailSelect.value,
      tone: toneSelect.value,
    };
    if (!alignedWeek) {
      setSettingsError("请选择第 1 周的日期");
      weekOneInput.focus();
      return;
    }
    settingsSaving = true;
    settingsSave.disabled = true;
    settingsSave.textContent = "保存中…";
    try {
      const res = await fetch("api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        throw new Error(await readErrorDetail(res, "保存失败"));
      }
      const data = await res.json();
      settingsState = data;
      settingsDraft = cloneSettings(data.settings || {});
      updateTopWeekInfo(data);
      settingsSaving = false;
      settingsSave.disabled = false;
      settingsSave.textContent = "保存设置";
      reset();
      loadHistory();
      loadTemplates();
      setDrawerView("main");
      syncSend();
      toast("设置已保存");
    } catch (e) {
      settingsSaving = false;
      settingsSave.disabled = false;
      settingsSave.textContent = "保存设置";
      setSettingsError(e.message);
    }
  }

  function activeTemplate() {
    return (
      templatesState.templates.find(function (item) {
        return Number(item.id) === Number(activeTemplateId);
      }) || null
    );
  }

  function updateTemplateModeUI() {
    const selected = activeTemplate();
    weeklyTemplateBtn.classList.toggle("active", !selected);
    if (!selected) weeklyTemplateBtn.setAttribute("aria-current", "page");
    else weeklyTemplateBtn.removeAttribute("aria-current");
    savedTemplateNav.querySelectorAll("[data-template-select]").forEach(function (button) {
      const active = Number(button.dataset.templateSelect) === Number(activeTemplateId);
      button.classList.toggle("active", active);
      if (active) button.setAttribute("aria-current", "page");
      else button.removeAttribute("aria-current");
    });
    heroOutputName.textContent = selected ? selected.name + " · 自定义文档" : "工作汇报 + 技术总结";
    heroSub.textContent = selected
      ? "和我聊聊这周的内容，我会按“" + selected.name + "”逐步补全并整理。"
      : "和我聊聊这周的工作、学习与比赛，我会逐步补全信息，整理成周报和技术总结。";
    input.placeholder = selected
      ? "输入本周内容，按“" + selected.name + "”整理"
      : "输入本周内容，或添加附件";
  }

  function renderTemplateNav() {
    savedTemplateNav.innerHTML = "";
    templatesState.templates.forEach(function (item) {
      const row = document.createElement("div");
      row.className = "template-nav-saved";
      row.innerHTML =
        '<button class="template-nav-item" type="button" data-template-select="' +
        item.id +
        '"><span class="template-nav-icon">模</span><span><strong>' +
        esc(item.name) +
        "</strong><small>自定义文档</small></span></button>" +
        '<div class="template-nav-manage"><button type="button" data-template-edit="' +
        item.id +
        '" aria-label="编辑 ' +
        escAttr(item.name) +
        '">编辑</button><button type="button" data-template-rename="' +
        item.id +
        '" aria-label="重命名 ' +
        escAttr(item.name) +
        '">改名</button><button type="button" data-template-delete="' +
        item.id +
        '" aria-label="删除 ' +
        escAttr(item.name) +
        '">删除</button></div>';
      savedTemplateNav.appendChild(row);
    });
    legacyTemplateDrafts.innerHTML = "";
    legacyTemplateDrafts.hidden = templatesState.drafts.length === 0;
    templatesState.drafts.forEach(function (item) {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.templateEdit = item.id;
      button.innerHTML =
        "<span>待确认</span><strong>" + esc(item.name || "旧版自定义模板") + "</strong>";
      legacyTemplateDrafts.appendChild(button);
    });
    updateTemplateModeUI();
  }

  async function loadTemplates() {
    if (!(settingsState && settingsState.configured)) return;
    try {
      const res = await fetch("api/templates");
      if (!res.ok) throw new Error(await readErrorDetail(res, "模板加载失败"));
      templatesState = await res.json();
      activeTemplateId = templatesState.selected_template_id || null;
      if (activeTemplateId && !activeTemplate()) activeTemplateId = null;
      renderTemplateNav();
    } catch (e) {
      toast("模板加载失败：" + e.message);
    }
  }

  async function selectTemplate(templateId) {
    const nextId = templateId ? Number(templateId) : null;
    if (Number(activeTemplateId || 0) === Number(nextId || 0)) {
      closeDrawer();
      return;
    }
    if (!confirmConversationSwitch("切换模板")) return;
    try {
      const res = await fetch("api/settings/template-selection", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ template_id: nextId }),
      });
      if (!res.ok) throw new Error(await readErrorDetail(res, "模板切换失败"));
      activeTemplateId = nextId;
      templatesState.selected_template_id = nextId;
      reset();
      updateTemplateModeUI();
      closeDrawer();
      toast(nextId ? "已切换到“" + activeTemplate().name + "”" : "已切换到周报");
    } catch (e) {
      toast(e.message);
    }
  }

  function showTemplateWorkspace(view) {
    document.body.classList.add("template-workspace-open");
    templateWorkspace.hidden = false;
    templateStart.hidden = view !== "start";
    templateLearn.hidden = view !== "learn";
    templateEditor.hidden = view !== "editor";
    templateSaveBtn.hidden = view !== "editor";
    closeDrawer();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function openTemplateWorkspace() {
    if (!confirmConversationSwitch("打开自定义模板")) return;
    reset();
    templateDraft = null;
    templateDraftDirty = false;
    templateWorkspaceTitle.textContent = "创建模板";
    templateAiMessages.innerHTML = "";
    clearTemplateSamples(true);
    showTemplateWorkspace("start");
  }

  function closeTemplateWorkspace(force) {
    if (!force && templateDraft && !window.confirm("当前模板尚未保存，确定返回吗？")) return;
    const abandoned = !force ? templateDraft : null;
    document.body.classList.remove("template-workspace-open");
    templateWorkspace.hidden = true;
    templateDraft = null;
    templateDraftDirty = false;
    clearTimeout(templatePersistTimer);
    clearTemplateSamples(true);
    if (abandoned)
      fetch("api/template-drafts/" + encodeURIComponent(abandoned.id), { method: "DELETE" }).catch(
        function () {}
      );
    showHero();
  }

  function showTemplateLearn() {
    templateLearnResult.textContent = "";
    showTemplateWorkspace("learn");
  }

  function renderTemplateSamples() {
    templateSampleList.innerHTML = "";
    templateSamples.forEach(function (item) {
      const row = document.createElement("div");
      row.className = "template-sample " + item.status;
      row.innerHTML =
        '<span class="template-sample-kind">文</span><span><strong>' +
        esc(item.name) +
        "</strong><small>" +
        (item.status === "uploading"
          ? "正在读取"
          : item.status === "error"
            ? esc(item.error || "读取失败")
            : esc(item.summary || "读取完成")) +
        '</small></span><button type="button" data-template-sample-remove="' +
        escAttr(item.localId) +
        '" aria-label="移除">×</button>';
      templateSampleList.appendChild(row);
    });
    const ready = templateSamples.filter(function (item) {
      return item.status === "ready";
    }).length;
    const pending = templateSamples.some(function (item) {
      return item.status === "uploading";
    });
    templateAnalyzeBtn.disabled = pending || ready < 1 || ready > 5 || templateBusy;
  }

  async function uploadTemplateFile(file) {
    if (!file || !file.name) return;
    if (templateSamples.length >= 5) {
      toast("模板学习最多上传 5 个文件");
      return;
    }
    if (file.size > MAX_ATTACHMENT_SIZE) {
      toast(file.name + " 超过 16MB");
      return;
    }
    if (!/\.(docx|pdf|pptx|xlsx|csv|txt|md|markdown)$/i.test(file.name)) {
      toast(file.name + " 的格式不能用于模板学习");
      return;
    }
    const item = {
      localId: "sample-" + Date.now() + "-" + Math.random().toString(16).slice(2),
      name: file.name,
      status: "uploading",
    };
    templateSamples.push(item);
    renderTemplateSamples();
    const body = new FormData();
    body.append("session_id", templateUploadSessionId);
    body.append("file", file, file.name);
    try {
      const res = await fetch("api/attachments", { method: "POST", body: body });
      if (!res.ok) throw new Error(await readErrorDetail(res, "文件读取失败"));
      Object.assign(item, await res.json(), { status: "ready" });
    } catch (e) {
      item.status = "error";
      item.error = e.message;
    }
    renderTemplateSamples();
  }

  function handleTemplateFiles(files) {
    const incoming = Array.from(files || []);
    const remaining = Math.max(0, 5 - templateSamples.length);
    if (incoming.length > remaining) toast("模板学习最多上传 5 个文件，超出的文件未添加");
    incoming.slice(0, remaining).forEach(uploadTemplateFile);
  }

  async function removeTemplateSample(localId) {
    const item = templateSamples.find(function (entry) {
      return entry.localId === localId;
    });
    templateSamples = templateSamples.filter(function (entry) {
      return entry.localId !== localId;
    });
    renderTemplateSamples();
    if (item && item.id) {
      fetch(
        "api/attachments/" +
          encodeURIComponent(item.id) +
          "?session_id=" +
          encodeURIComponent(templateUploadSessionId),
        { method: "DELETE" }
      ).catch(function () {});
    }
  }

  function clearTemplateSamples(deleteRemote) {
    const previous = templateSamples.slice();
    templateSamples = [];
    renderTemplateSamples();
    if (deleteRemote)
      previous.forEach(function (item) {
        if (item.id)
          fetch(
            "api/attachments/" +
              encodeURIComponent(item.id) +
              "?session_id=" +
              encodeURIComponent(templateUploadSessionId),
            { method: "DELETE" }
          ).catch(function () {});
      });
    templateUploadSessionId = newSessionId();
  }

  function templateId(prefix) {
    return prefix + "_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 7);
  }

  function blockTypeName(type) {
    return (
      {
        paragraph: "段落",
        field: "字段",
        bullet_list: "项目列表",
        numbered_list: "编号列表",
        table: "表格",
      }[type] || type
    );
  }

  function blockTypeOptions(selected) {
    return ["paragraph", "field", "bullet_list", "numbered_list", "table"]
      .map(function (type) {
        return (
          '<option value="' +
          type +
          '"' +
          (type === selected ? " selected" : "") +
          ">" +
          blockTypeName(type) +
          "</option>"
        );
      })
      .join("");
  }

  function renderTemplateStructureEditor() {
    if (!templateDraft) return;
    const definition = templateDraft.definition;
    templateTitlePattern.value = definition.title_pattern || "";
    let html = "";
    definition.sections.forEach(function (section, sectionIndex) {
      html += '<article class="template-section-editor" data-section-index="' + sectionIndex + '">';
      html +=
        '<div class="template-section-head"><span>章节 ' + (sectionIndex + 1) + "</span><div>";
      html +=
        '<button type="button" data-section-move="up"' +
        (sectionIndex === 0 ? " disabled" : "") +
        ">↑</button>";
      html +=
        '<button type="button" data-section-move="down"' +
        (sectionIndex === definition.sections.length - 1 ? " disabled" : "") +
        ">↓</button>";
      html += '<button type="button" data-section-remove>删除</button></div></div>';
      html +=
        '<label>章节名称<input data-section-field="title" maxlength="100" value="' +
        escAttr(section.title) +
        '"></label>';
      html +=
        '<label>章节说明<textarea data-section-field="description" rows="2" maxlength="500">' +
        esc(section.description || "") +
        "</textarea></label>";
      html += '<div class="template-blocks-editor">';
      section.blocks.forEach(function (block, blockIndex) {
        html += '<div class="template-block-editor" data-block-index="' + blockIndex + '">';
        html +=
          '<div class="template-block-head"><select data-block-field="type">' +
          blockTypeOptions(block.type) +
          "</select><div>";
        html +=
          '<button type="button" data-block-move="up"' +
          (blockIndex === 0 ? " disabled" : "") +
          ">↑</button>";
        html +=
          '<button type="button" data-block-move="down"' +
          (blockIndex === section.blocks.length - 1 ? " disabled" : "") +
          ">↓</button>";
        html += '<button type="button" data-block-remove>删除</button></div></div>';
        html +=
          '<label>显示名称<input data-block-field="label" maxlength="100" value="' +
          escAttr(block.label) +
          '"></label>';
        html +=
          '<label>AI 填写说明<textarea data-block-field="instruction" rows="2" maxlength="500">' +
          esc(block.instruction || "") +
          "</textarea></label>";
        html +=
          '<label class="template-required"><input data-block-field="required" type="checkbox"' +
          (block.required ? " checked" : "") +
          "> 必填内容</label>";
        if (block.type === "table") {
          html += '<div class="template-columns"><strong>表格列</strong>';
          (block.columns || []).forEach(function (column, columnIndex) {
            html +=
              '<div class="template-column" data-column-index="' +
              columnIndex +
              '"><input data-column-field="label" maxlength="100" value="' +
              escAttr(column.label) +
              '" placeholder="列名"><input data-column-field="instruction" maxlength="500" value="' +
              escAttr(column.instruction || "") +
              '" placeholder="这一列填写什么"><button type="button" data-column-remove aria-label="删除列">×</button></div>';
          });
          html +=
            '<button class="mini-btn" type="button" data-column-add>+ 添加一列</button></div>';
        }
        html += "</div>";
      });
      html +=
        '</div><div class="template-add-block"><select data-new-block-type>' +
        blockTypeOptions("paragraph") +
        '</select><button class="mini-btn" type="button" data-block-add>+ 添加内容块</button></div>';
      html += "</article>";
    });
    templateSectionsEditor.innerHTML = html;
    renderTemplatePreview();
  }

  function placeholderTitle(pattern) {
    return String(pattern || "自定义汇报")
      .replace(/\{week_number\}/g, "1")
      .replace(/\{date_range\}/g, "2026.08.24–2026.08.30")
      .replace(/\{week_start\}/g, "2026-08-24")
      .replace(/\{week_end\}/g, "2026-08-30");
  }

  function renderTemplatePreview() {
    if (!templateDraft) return;
    const definition = templateDraft.definition;
    let html = "<h1>" + esc(placeholderTitle(definition.title_pattern)) + "</h1>";
    definition.sections.forEach(function (section, index) {
      html += "<section><h2>" + (index + 1) + ". " + esc(section.title || "未命名章节") + "</h2>";
      section.blocks.forEach(function (block) {
        const label = esc(block.label || "内容");
        if (block.type === "paragraph")
          html +=
            '<div class="preview-block"><strong>' +
            label +
            "</strong><p>这里将展示" +
            label +
            "。</p></div>";
        else if (block.type === "field")
          html +=
            '<p class="preview-field"><strong>' + label + "：</strong>这里将展示" + label + "</p>";
        else if (block.type === "bullet_list" || block.type === "numbered_list") {
          const tag = block.type === "numbered_list" ? "ol" : "ul";
          html +=
            '<div class="preview-block"><strong>' +
            label +
            "</strong><" +
            tag +
            "><li>" +
            label +
            "示例一</li><li>" +
            label +
            "示例二</li></" +
            tag +
            "></div>";
        } else if (block.type === "table") {
          html +=
            '<div class="preview-block"><strong>' +
            label +
            '</strong><div class="preview-table-wrap"><table><thead><tr>';
          (block.columns || []).forEach(function (column) {
            html += "<th>" + esc(column.label) + "</th>";
          });
          html += "</tr></thead><tbody><tr>";
          (block.columns || []).forEach(function (column) {
            html += "<td>" + esc(column.label) + "示例</td>";
          });
          html += "</tr></tbody></table></div></div>";
        }
      });
      html += "</section>";
    });
    templatePreview.innerHTML = html;
  }

  function scheduleTemplatePersist() {
    templateDraftDirty = true;
    templateDraftEditVersion += 1;
    renderTemplatePreview();
    clearTimeout(templatePersistTimer);
    templatePersistTimer = setTimeout(function () {
      persistTemplateDraft().catch(function (error) {
        toast(error.message);
      });
    }, 650);
  }

  async function persistTemplateDraft() {
    if (!templateDraft || !templateDraftDirty) return;
    clearTimeout(templatePersistTimer);
    if (templatePersistInFlight) {
      await templatePersistInFlight;
      if (templateDraft && templateDraftDirty) return persistTemplateDraft();
      return;
    }
    const draft = templateDraft;
    const editVersion = templateDraftEditVersion;
    const definition = JSON.parse(JSON.stringify(draft.definition));
    const payload = { definition: definition };
    if (Number.isInteger(draft.revision)) payload.base_revision = draft.revision;
    templatePersistInFlight = (async function () {
      const res = await fetch("api/template-drafts/" + encodeURIComponent(draft.id), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(await readErrorDetail(res, "模板草稿保存失败"));
      return res.json();
    })();
    try {
      const saved = await templatePersistInFlight;
      if (templateDraft !== draft) return saved;
      draft.revision = saved.revision;
      if (templateDraftEditVersion === editVersion) {
        draft.definition = saved.definition;
        templateDraftDirty = false;
      }
      return saved;
    } catch (error) {
      if (templateDraft === draft) templateDraftDirty = true;
      throw error;
    } finally {
      templatePersistInFlight = null;
    }
  }

  function enterTemplateEditor(draft) {
    templateDraft = draft;
    templateDraftDirty = false;
    templateDraftEditVersion = 0;
    templateWorkspaceTitle.textContent = draft.source_template_id ? "编辑模板" : "创建模板";
    templateAiMessages.innerHTML = "";
    showTemplateWorkspace("editor");
    renderTemplateStructureEditor();
  }

  async function startManualTemplate() {
    if (templateBusy) return;
    templateBusy = true;
    try {
      const res = await fetch("api/template-drafts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_type: "manual" }),
      });
      if (!res.ok) throw new Error(await readErrorDetail(res, "草稿创建失败"));
      enterTemplateEditor(await res.json());
    } catch (e) {
      toast(e.message);
    }
    templateBusy = false;
  }

  async function analyzeTemplateSamples() {
    if (templateBusy) return;
    const ready = templateSamples.filter(function (item) {
      return item.status === "ready";
    });
    if (!ready.length || ready.length > 5) return;
    templateBusy = true;
    templateAnalyzeBtn.disabled = true;
    templateAnalyzeBtn.textContent = "正在分析…";
    templateLearnResult.className = "template-learn-result";
    templateLearnResult.textContent = "DeepSeek 正在比较文档结构并提取共同格式…";
    try {
      const res = await fetch("api/template-drafts/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: templateUploadSessionId,
          attachment_ids: ready.map(function (item) {
            return item.id;
          }),
        }),
      });
      if (!res.ok) {
        const detail = await readErrorDetail(res, "模板分析失败");
        if (res.status === 429) {
          showQuotaDialog(res, detail);
          return;
        }
        throw new Error(detail);
      }
      const data = await res.json();
      if (data.status === "incompatible") {
        templateLearnResult.className = "template-learn-result incompatible";
        templateLearnResult.textContent = "这些文件差异较大，暂时无法提取共同结构：" + data.reason;
      } else {
        enterTemplateEditor(data.draft);
        (data.warnings || []).forEach(function (warning) {
          addTemplateAiMessage("ai", "差异提示：" + warning);
        });
      }
    } catch (e) {
      templateLearnResult.className = "template-learn-result incompatible";
      templateLearnResult.textContent = e.message;
    } finally {
      templateBusy = false;
      templateAnalyzeBtn.textContent = "AI 分析格式";
      renderTemplateSamples();
    }
  }

  async function editTemplate(templateId) {
    if (!confirmConversationSwitch("编辑模板")) return;
    try {
      reset();
      const res = await fetch("api/templates/" + templateId + "/edit-draft", { method: "POST" });
      if (!res.ok) throw new Error(await readErrorDetail(res, "模板载入失败"));
      closeDrawer();
      enterTemplateEditor(await res.json());
    } catch (e) {
      toast(e.message);
    }
  }

  function addTemplateAiMessage(role, text) {
    const item = document.createElement("div");
    item.className = "template-ai-message " + role;
    item.textContent = text;
    templateAiMessages.appendChild(item);
    templateAiMessages.scrollTop = templateAiMessages.scrollHeight;
    return item;
  }

  async function reviseTemplateWithAi() {
    const message = templateAiInput.value.trim();
    if (!templateDraft || !message || templateBusy) return;
    const activeDraft = templateDraft;
    templateBusy = true;
    templateAiSend.disabled = true;
    templateSaveBtn.disabled = true;
    templateEditorPane.inert = true;
    templateEditorPane.setAttribute("aria-busy", "true");
    addTemplateAiMessage("user", message);
    templateAiInput.value = "";
    const aiItem = addTemplateAiMessage("ai", "正在调整模板…");
    try {
      await persistTemplateDraft();
      if (templateDraft !== activeDraft) throw new Error("模板草稿已切换，本次 AI 修改未应用");
      const aiBaseEditVersion = templateDraftEditVersion;
      const res = await fetch(
        "api/template-drafts/" + encodeURIComponent(templateDraft.id) + "/chat",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: message, base_revision: templateDraft.revision }),
        }
      );
      if (!res.ok || !res.body) {
        const detail = await readErrorDetail(res, "AI 修改失败");
        if (res.status === 429) {
          showQuotaDialog(res, detail);
          aiItem.remove();
          return;
        }
        throw new Error(detail);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let reply = "";
      while (true) {
        const chunk = await reader.read();
        if (chunk.done) buffer += decoder.decode();
        else buffer += decoder.decode(chunk.value, { stream: true });
        buffer = consumeSseBuffer(
          buffer,
          function (event) {
            if (event.type === "delta") {
              reply += event.text || "";
              aiItem.textContent = reply;
            } else if (event.type === "template") {
              if (templateDraft !== activeDraft || templateDraftEditVersion !== aiBaseEditVersion) {
                throw new Error("AI 修改期间模板又发生了变化，请重新操作");
              }
              templateDraft = event.draft;
              templateDraftDirty = false;
              renderTemplateStructureEditor();
            } else if (event.type === "error") throw new Error(event.message || "AI 修改失败");
          },
          chunk.done
        );
        if (chunk.done) break;
      }
    } catch (e) {
      aiItem.textContent = "修改失败：" + e.message;
    } finally {
      templateBusy = false;
      templateAiSend.disabled = false;
      templateSaveBtn.disabled = false;
      templateEditorPane.inert = false;
      templateEditorPane.removeAttribute("aria-busy");
    }
  }

  function openTemplateNameDialog() {
    if (!templateDraft || templateBusy) return;
    templateNameError.hidden = true;
    templateNameError.textContent = "";
    templateNameInput.value = templateDraft.suggested_name || "";
    if (templateNameDialog.showModal) templateNameDialog.showModal();
    else templateNameDialog.setAttribute("open", "");
    setTimeout(function () {
      templateNameInput.focus();
    }, 0);
  }

  function closeTemplateNameDialog() {
    if (templateNameDialog.close) templateNameDialog.close();
    else templateNameDialog.removeAttribute("open");
  }

  async function saveNamedTemplate() {
    if (!templateDraft || templateNameSaving) return;
    const name = templateNameInput.value.trim();
    if (!name) {
      templateNameError.textContent = "请输入模板名称";
      templateNameError.hidden = false;
      return;
    }
    if (["周报", "自定义"].indexOf(name) !== -1) {
      templateNameError.textContent = "不能使用“周报”或“自定义”作为名称";
      templateNameError.hidden = false;
      return;
    }
    templateNameSaving = true;
    try {
      await persistTemplateDraft();
      const targetId = templateDraft.source_template_id;
      const res = await fetch(targetId ? "api/templates/" + targetId : "api/templates", {
        method: targetId ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          draft_id: templateDraft.id,
          draft_revision: templateDraft.revision,
          name: name,
        }),
      });
      if (!res.ok) throw new Error(await readErrorDetail(res, "模板保存失败"));
      const saved = await res.json();
      activeTemplateId = saved.id;
      closeTemplateNameDialog();
      templateDraftDirty = false;
      closeTemplateWorkspace(true);
      reset();
      await loadTemplates();
      toast("模板“" + saved.name + "”已保存并选中");
    } catch (e) {
      templateNameError.textContent = e.message;
      templateNameError.hidden = false;
    } finally {
      templateNameSaving = false;
    }
  }

  async function renameTemplate(templateId) {
    const item = templatesState.templates.find(function (entry) {
      return Number(entry.id) === Number(templateId);
    });
    if (!item) return;
    const name = window.prompt("请输入新的模板名称", item.name);
    if (name == null || !name.trim() || name.trim() === item.name) return;
    try {
      const res = await fetch("api/templates/" + templateId, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim() }),
      });
      if (!res.ok) throw new Error(await readErrorDetail(res, "重命名失败"));
      await loadTemplates();
      toast("模板已重命名");
    } catch (e) {
      toast(e.message);
    }
  }

  async function deleteTemplateItem(templateId) {
    const item = templatesState.templates.find(function (entry) {
      return Number(entry.id) === Number(templateId);
    });
    if (!item || !window.confirm("删除模板“" + item.name + "”？历史记录和历史导出不会受影响。"))
      return;
    try {
      const res = await fetch("api/templates/" + templateId, { method: "DELETE" });
      if (!res.ok) throw new Error(await readErrorDetail(res, "删除失败"));
      if (Number(activeTemplateId) === Number(templateId)) {
        activeTemplateId = null;
        reset();
      }
      await loadTemplates();
      toast("模板已删除");
    } catch (e) {
      toast(e.message);
    }
  }

  function moveArrayItem(items, index, direction) {
    const next = index + direction;
    if (next < 0 || next >= items.length) return;
    const current = items[index];
    items[index] = items[next];
    items[next] = current;
  }

  function newTemplateBlock(type) {
    return {
      id: templateId("block"),
      type: type,
      label: blockTypeName(type),
      instruction: "",
      required: false,
      columns:
        type === "table" ? [{ id: templateId("column"), label: "列 1", instruction: "" }] : [],
    };
  }

  function openDrawer(view) {
    if (!settingsLoaded) return;
    drawerReturnFocus = document.activeElement;
    drawer.classList.add("open");
    overlay.classList.add("open");
    setDrawerView(view || "main");
    loadHistory();
  }
  function closeDrawer() {
    if (!(settingsState && settingsState.configured)) return;
    drawer.classList.remove("open");
    overlay.classList.remove("open");
    setDrawerView("main", false);
    if (drawerReturnFocus && drawerReturnFocus.focus) drawerReturnFocus.focus();
  }
  function hideHero() {
    hero.classList.add("hide");
  }
  function showHero() {
    hero.classList.remove("hide");
  }

  function scrollBottom() {
    window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
  }

  function addUserBubble(text, attachmentItems) {
    const wrap = document.createElement("div");
    wrap.className = "msg user";
    const b = document.createElement("div");
    b.className = "bubble";
    b.classList.toggle("has-attachments", Boolean(attachmentItems && attachmentItems.length));
    b.classList.toggle(
      "attachments-only",
      Boolean(!text && attachmentItems && attachmentItems.length)
    );
    if (text) {
      const copy = document.createElement("div");
      copy.className = "message-copy";
      copy.textContent = text;
      b.appendChild(copy);
    }
    const attachmentList = document.createElement("div");
    attachmentList.className = "sent-attachment-list";
    (attachmentItems || []).forEach(function (item) {
      const kind = attachmentKind(item);
      if (kind.className === "image" && item.previewUrl) {
        sentAttachmentPreviewUrls.add(item.previewUrl);
        const preview = document.createElement("a");
        preview.className = "sent-image";
        preview.href = item.previewUrl;
        preview.target = "_blank";
        preview.rel = "noopener";
        preview.title = "查看原图";
        const image = document.createElement("img");
        image.src = item.previewUrl;
        image.alt = "已发送图片：" + item.name;
        image.decoding = "async";
        const caption = document.createElement("span");
        caption.className = "sent-image-caption";
        caption.textContent = item.name;
        preview.appendChild(image);
        preview.appendChild(caption);
        attachmentList.appendChild(preview);
        return;
      }
      const file = document.createElement("div");
      file.className = "sent-file";
      const icon = createAttachmentIcon("sent-attachment-icon", kind);
      const fileCopy = document.createElement("span");
      fileCopy.className = "sent-file-copy";
      const fileName = document.createElement("strong");
      fileName.textContent = item.name;
      fileName.title = item.name;
      const fileMeta = document.createElement("small");
      fileMeta.textContent = sentAttachmentMeta(item);
      fileCopy.appendChild(fileName);
      fileCopy.appendChild(fileMeta);
      const ready = document.createElement("span");
      ready.className = "sent-file-state";
      ready.textContent = "已读取";
      file.appendChild(icon);
      file.appendChild(fileCopy);
      file.appendChild(ready);
      attachmentList.appendChild(file);
    });
    if (attachmentList.childElementCount) b.appendChild(attachmentList);
    wrap.appendChild(b);
    messages.appendChild(wrap);
    scrollBottom();
    return wrap;
  }

  function addAiBubble() {
    const wrap = document.createElement("div");
    wrap.className = "msg ai";
    const b = document.createElement("div");
    b.className = "bubble";
    b.innerHTML = '<span class="typing"><span></span><span></span><span></span></span>';
    wrap.appendChild(b);
    messages.appendChild(wrap);
    scrollBottom();
    return b;
  }

  function setBubbleText(bubble, text) {
    bubble.textContent = text;
    scrollBottom();
  }

  function renderReportCard(report) {
    const dl = currentWeekId ? "api/weeks/" + currentWeekId + "/export?doc=report" : "#";
    let html = '<section class="card">';
    html +=
      '<div class="card-head"><span class="card-kicker">工作汇报</span><a class="card-dl" href="' +
      dl +
      '" download>' +
      DOWNLOAD_ICON +
      "下载 Word</a></div>";
    html += '<h2 class="card-title">' + esc((report && report.title) || "工作汇报") + "</h2>";
    (report && report.sections ? report.sections : []).forEach(function (s) {
      html += '<div class="section"><span class="chip">' + esc(s.category || "其他") + "</span>";
      (s.items || []).forEach(function (it) {
        html += '<div class="item">';
        if (it.summary) html += '<div class="item-summary">' + esc(it.summary) + "</div>";
        if (it.date) html += '<div class="item-meta"><span>日期</span>' + esc(it.date) + "</div>";
        if (it.detail) html += '<div class="item-meta">' + esc(it.detail) + "</div>";
        if (it.result)
          html += '<div class="item-meta"><span>结果</span>' + esc(it.result) + "</div>";
        if (it.next_step)
          html += '<div class="item-meta"><span>下一步</span>' + esc(it.next_step) + "</div>";
        html += "</div>";
      });
      html += "</div>";
    });
    html += "</section>";
    return html;
  }

  function renderTechCard(tech) {
    const dl = currentWeekId ? "api/weeks/" + currentWeekId + "/export?doc=tech" : "#";
    let html = '<section class="card">';
    html +=
      '<div class="card-head"><span class="card-kicker">技术总结</span><a class="card-dl" href="' +
      dl +
      '" download>' +
      DOWNLOAD_ICON +
      "下载 Word</a></div>";
    html += '<h2 class="card-title">' + esc((tech && tech.title) || "技术总结") + "</h2>";
    const topics = (tech && tech.topics) || [];
    if (!topics.length) html += '<p class="empty">本周无明确技术内容。</p>';
    topics.forEach(function (tp) {
      html +=
        '<div class="topic"><div class="topic-name">' + esc(tp.topic || "未命名主题") + "</div>";
      if (tp.explanation) html += '<div class="topic-desc">' + esc(tp.explanation) + "</div>";
      (tp.key_points || []).forEach(function (kp) {
        html += '<div class="item-meta">' + esc(kp) + "</div>";
      });
      html += "</div>";
    });
    html += "</section>";
    return html;
  }

  function renderResult(organized, headerText) {
    result.hidden = false;
    let html = "";
    if (headerText) html += '<div class="result-head">' + esc(headerText) + "</div>";
    html += renderReportCard(organized.report) + renderTechCard(organized.tech_summary);
    result.innerHTML = html;
    scrollBottom();
  }

  function renderCustomResult(definition, document, templateName, headerText) {
    const dl = currentWeekId ? "api/weeks/" + currentWeekId + "/export?doc=custom" : "#";
    const sectionValues = {};
    (document.sections || []).forEach(function (section) {
      sectionValues[section.id] = section;
    });
    let html = "";
    if (headerText) html += '<div class="result-head">' + esc(headerText) + "</div>";
    html +=
      '<section class="card custom-result-card"><div class="card-head"><span class="card-kicker">' +
      esc(templateName || "自定义") +
      '</span><a class="card-dl" href="' +
      dl +
      '" download>' +
      DOWNLOAD_ICON +
      "下载 Word</a></div>";
    html +=
      '<h2 class="card-title">' + esc(document.title || templateName || "自定义汇报") + "</h2>";
    (definition.sections || []).forEach(function (section) {
      const supplied = sectionValues[section.id] || { blocks: [] };
      const values = {};
      (supplied.blocks || []).forEach(function (block) {
        values[block.id] = block;
      });
      html += '<div class="section custom-document-section"><h3>' + esc(section.title) + "</h3>";
      (section.blocks || []).forEach(function (block) {
        const value = values[block.id] || {};
        if ((block.type === "paragraph" || block.type === "field") && value.text) {
          html +=
            '<div class="custom-value ' +
            block.type +
            '"><strong>' +
            esc(block.label) +
            (block.type === "field" ? "：" : "") +
            "</strong>" +
            (block.type === "paragraph" ? "<p>" : "<span>") +
            esc(value.text) +
            (block.type === "paragraph" ? "</p>" : "</span>") +
            "</div>";
        } else if (
          (block.type === "bullet_list" || block.type === "numbered_list") &&
          (value.items || []).length
        ) {
          const tag = block.type === "numbered_list" ? "ol" : "ul";
          html +=
            '<div class="custom-value"><strong>' + esc(block.label) + "</strong><" + tag + ">";
          value.items.forEach(function (item) {
            html += "<li>" + esc(item) + "</li>";
          });
          html += "</" + tag + "></div>";
        } else if (block.type === "table" && (value.rows || []).length) {
          html +=
            '<div class="custom-value"><strong>' +
            esc(block.label) +
            '</strong><div class="preview-table-wrap"><table><thead><tr>';
          (block.columns || []).forEach(function (column) {
            html += "<th>" + esc(column.label) + "</th>";
          });
          html += "</tr></thead><tbody>";
          value.rows.forEach(function (row) {
            html += "<tr>";
            (block.columns || []).forEach(function (column) {
              html += "<td>" + esc(row[column.id] || "") + "</td>";
            });
            html += "</tr>";
          });
          html += "</tbody></table></div></div>";
        }
      });
      html += "</div>";
    });
    html += "</section>";
    result.hidden = false;
    result.innerHTML = html;
    scrollBottom();
  }

  function handleEvent(ev, aiBubble, aiText) {
    if (ev.type === "delta") {
      aiText.value += ev.text;
      setBubbleText(aiBubble, aiText.value);
    } else if (ev.type === "final") {
      currentWeekId = ev.week_id;
      currentSessionDirty = false;
      if (ev.output_kind === "custom")
        renderCustomResult(
          ev.definition,
          ev.document,
          ev.template_name,
          "已按自定义模板整理好，可下载 Word"
        );
      else renderResult(ev.organized, "已为你整理好，可下载 Word");
    } else if (ev.type === "error") {
      toast(ev.message || "出错了");
    }
  }

  async function sendMessage() {
    if (isStreaming) return;
    if (!(settingsState && settingsState.configured)) {
      openStartupSetup();
      return;
    }
    const text = input.value.trim();
    const sentAttachments = selectedAttachments.filter(function (item) {
      return item.status === "ready";
    });
    if (!text && !sentAttachments.length) return;
    if (
      selectedAttachments.some(function (item) {
        return item.status === "uploading";
      })
    ) {
      toast("请等待附件读取完成");
      return;
    }
    isStreaming = true;
    syncSend();
    let aiBubble = null;
    const aiText = { value: "" };

    try {
      const res = await fetch("api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          message: text,
          attachment_ids: sentAttachments.map(function (item) {
            return item.id;
          }),
          mode: chatMode,
          template_id: activeTemplateId,
        }),
      });
      if (!res.ok || !res.body) {
        const detail = await readErrorDetail(res, "请求失败 " + res.status);
        if (res.status === 429) {
          showQuotaDialog(res, detail);
          return;
        }
        throw new Error(detail);
      }
      currentSessionDirty = true;
      addUserBubble(text, sentAttachments);
      input.value = "";
      clearAttachments(false);
      autoGrow();
      hideHero();
      aiBubble = addAiBubble();
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let ended = false;
      while (!ended) {
        const chunk = await reader.read();
        if (chunk.done) {
          buffer += decoder.decode();
          ended = true;
        } else {
          buffer += decoder.decode(chunk.value, { stream: true });
        }
        buffer = consumeSseBuffer(
          buffer,
          function (event) {
            handleEvent(event, aiBubble, aiText);
          },
          chunk.done
        );
      }
    } catch (e) {
      if (aiBubble && !aiText.value) setBubbleText(aiBubble, "");
      toast("错误：" + e.message);
    } finally {
      isStreaming = false;
      syncSend();
      loadHistory();
    }
  }

  function hasUnarchivedContent() {
    return Boolean(input.value.trim() || selectedAttachments.length || currentSessionDirty);
  }

  function confirmConversationSwitch(action) {
    if (isStreaming) {
      toast("请等待当前回复完成");
      return false;
    }
    if (!hasUnarchivedContent()) return true;
    return window.confirm("当前有尚未归档的内容，" + action + "会清空这些内容，继续吗？");
  }

  async function loadHistory() {
    try {
      if (!settingsLoaded) return;
      const res = await fetch("api/weeks");
      if (res.status === 409) {
        history.innerHTML = '<div class="drawer-empty">请先完成首次设置</div>';
        return;
      }
      if (!res.ok) {
        throw new Error(await readErrorDetail(res, "历史加载失败"));
      }
      const weeks = await res.json();
      history.innerHTML = "";
      if (!weeks.length) {
        history.innerHTML = '<div class="drawer-empty">还没有记录</div>';
        return;
      }
      weeks.forEach(function (w) {
        const b = document.createElement("button");
        b.className = "history-item";
        const label = w.display_label || "第 " + (w.week_number || "?") + " 周";
        const range = w.week_start && w.week_end ? formatRange(w.week_start) : w.week_start;
        const isCurrent = Boolean(
          settingsState &&
          settingsState.current_week &&
          w.week_start === settingsState.current_week.week_start
        );
        const isActive = Number(w.id) === Number(currentWeekId);
        b.classList.toggle("current", isCurrent);
        b.classList.toggle("active", isActive);
        if (isActive) b.setAttribute("aria-current", "page");
        const updated = String(w.updated_at || "")
          .slice(0, 16)
          .replace("T", " ");
        b.innerHTML =
          '<span class="hi-row"><span class="hi-week">' +
          esc(label) +
          "</span>" +
          (isCurrent ? '<span class="hi-badge">本周</span>' : "") +
          '</span><span class="hi-time">' +
          esc(range || "") +
          "</span>" +
          (updated ? '<span class="hi-updated">更新于 ' + esc(updated) + "</span>" : "");
        b.onclick = function () {
          openWeek(w.id);
        };
        history.appendChild(b);
      });
    } catch (e) {
      /* 忽略 */
    }
  }

  async function loadPrivacy() {
    if (!privacySummary) return;
    try {
      const res = await fetch("api/privacy");
      if (!res.ok) return;
      const value = await res.json();
      const reportText = value.report_retention_days
        ? "周报保存 " + value.report_retention_days + " 天"
        : "周报不会自动删除";
      const processors = (value.processors || [])
        .map(function (item) {
          return item.name + "用于" + item.purpose;
        })
        .join("，");
      privacySummary.textContent =
        "附件和模板样例原文件不写入业务数据库；提取文字、未完成对话和模板草稿会在 SQLite 中最多暂存 " +
        Math.round((value.attachment_ttl_seconds || 0) / 3600) +
        " 小时，归档或删除数据时立即清除；" +
        reportText +
        "。" +
        (processors ? "处理过程中会发送给第三方服务：" + processors + "。" : "") +
        "你可以随时删除本浏览器身份下的全部数据。";
    } catch (e) {
      /* 保留静态说明 */
    }
  }

  async function deleteAllData() {
    if (!window.confirm("这会永久删除本浏览器的全部周报、版本和设置，且无法撤销。确定继续吗？"))
      return;
    deleteDataBtn.disabled = true;
    try {
      const res = await fetch("api/data", { method: "DELETE" });
      if (!res.ok) throw new Error(await readErrorDetail(res, "删除失败"));
      window.location.reload();
    } catch (e) {
      deleteDataBtn.disabled = false;
      toast("删除失败：" + e.message);
    }
  }

  async function openWeek(id) {
    if (Number(id) === Number(currentWeekId)) {
      closeDrawer();
      return;
    }
    if (!confirmConversationSwitch("切换历史记录")) return;
    try {
      const res = await fetch("api/weeks/" + id);
      if (!res.ok) return;
      const w = await res.json();
      currentWeekId = w.id;
      currentSessionDirty = false;
      hideHero();
      releaseSentAttachmentPreviews();
      messages.innerHTML = "";
      const label = w.display_label || "第 " + (w.week_number || "?") + " 周";
      const range = w.week_start && w.week_end ? formatRange(w.week_start) : w.week_start;
      if (w.output_kind === "custom")
        renderCustomResult(
          w.definition,
          w.document,
          w.template_name,
          "已归档 · " + label + " · " + (range || w.week_start)
        );
      else renderResult(w.report, "已归档 · " + label + " · " + (range || w.week_start));
      closeDrawer();
    } catch (e) {
      toast("载入失败：" + e.message);
    }
  }

  function reset() {
    clearAttachments(true);
    releaseSentAttachmentPreviews();
    closeUploadMenu();
    sessionId = newSessionId();
    currentWeekId = null;
    messages.innerHTML = "";
    result.hidden = true;
    result.innerHTML = "";
    input.value = "";
    currentSessionDirty = false;
    autoGrow();
    syncSend();
    showHero();
  }

  menuBtn.addEventListener("click", function () {
    openDrawer("main");
  });
  drawerClose.addEventListener("click", closeDrawer);
  overlay.addEventListener("click", closeDrawer);
  drawerBack.addEventListener("click", function () {
    setDrawerView("main");
  });
  newBtn.addEventListener("click", function () {
    if (!confirmConversationSwitch("开始新记录")) return;
    reset();
    closeDrawer();
  });
  settingsBtn.addEventListener("click", function () {
    setDrawerView("settings");
  });
  helpBtn.addEventListener("click", function () {
    setDrawerView("help");
  });
  weeklyTemplateBtn.addEventListener("click", function () {
    selectTemplate(null);
  });
  customTemplateBtn.addEventListener("click", openTemplateWorkspace);
  savedTemplateNav.addEventListener("click", function (event) {
    const select = event.target.closest("[data-template-select]");
    const edit = event.target.closest("[data-template-edit]");
    const rename = event.target.closest("[data-template-rename]");
    const remove = event.target.closest("[data-template-delete]");
    if (edit) editTemplate(edit.dataset.templateEdit);
    else if (rename) renameTemplate(rename.dataset.templateRename);
    else if (remove) deleteTemplateItem(remove.dataset.templateDelete);
    else if (select) selectTemplate(select.dataset.templateSelect);
  });
  legacyTemplateDrafts.addEventListener("click", function (event) {
    const edit = event.target.closest("[data-template-edit]");
    if (edit) editTemplate(edit.dataset.templateEdit);
  });
  templateWorkspaceBack.addEventListener("click", function () {
    closeTemplateWorkspace(false);
  });
  templateManualBtn.addEventListener("click", startManualTemplate);
  templateLearnBtn.addEventListener("click", showTemplateLearn);
  templateLearnCancel.addEventListener("click", function () {
    clearTemplateSamples(true);
    showTemplateWorkspace("start");
  });
  templateFileBtn.addEventListener("click", function () {
    templateFileInput.click();
  });
  templateFileInput.addEventListener("change", function () {
    handleTemplateFiles(templateFileInput.files);
    templateFileInput.value = "";
  });
  templateSampleList.addEventListener("click", function (event) {
    const remove = event.target.closest("[data-template-sample-remove]");
    if (remove) removeTemplateSample(remove.dataset.templateSampleRemove);
  });
  templateAnalyzeBtn.addEventListener("click", analyzeTemplateSamples);
  templateLearnDrop.addEventListener("dragover", function (event) {
    event.preventDefault();
    templateLearnDrop.classList.add("dragging");
  });
  templateLearnDrop.addEventListener("dragleave", function () {
    templateLearnDrop.classList.remove("dragging");
  });
  templateLearnDrop.addEventListener("drop", function (event) {
    event.preventDefault();
    event.stopPropagation();
    templateLearnDrop.classList.remove("dragging");
    handleTemplateFiles(event.dataTransfer.files);
  });
  templateTitlePattern.addEventListener("input", function () {
    if (templateDraft) {
      templateDraft.definition.title_pattern = templateTitlePattern.value;
      scheduleTemplatePersist();
    }
  });
  templateAddSection.addEventListener("click", function () {
    if (!templateDraft || templateDraft.definition.sections.length >= 20) return;
    templateDraft.definition.sections.push({
      id: templateId("section"),
      title: "新章节",
      description: "",
      blocks: [newTemplateBlock("paragraph")],
    });
    scheduleTemplatePersist();
    renderTemplateStructureEditor();
  });
  templateSectionsEditor.addEventListener("input", function (event) {
    if (!templateDraft) return;
    const sectionNode = event.target.closest("[data-section-index]");
    if (!sectionNode) return;
    const section = templateDraft.definition.sections[Number(sectionNode.dataset.sectionIndex)];
    const blockNode = event.target.closest("[data-block-index]");
    const columnNode = event.target.closest("[data-column-index]");
    if (columnNode && blockNode && event.target.dataset.columnField) {
      section.blocks[Number(blockNode.dataset.blockIndex)].columns[
        Number(columnNode.dataset.columnIndex)
      ][event.target.dataset.columnField] = event.target.value;
    } else if (blockNode && event.target.dataset.blockField) {
      const block = section.blocks[Number(blockNode.dataset.blockIndex)];
      block[event.target.dataset.blockField] =
        event.target.dataset.blockField === "required" ? event.target.checked : event.target.value;
    } else if (event.target.dataset.sectionField)
      section[event.target.dataset.sectionField] = event.target.value;
    scheduleTemplatePersist();
  });
  templateSectionsEditor.addEventListener("change", function (event) {
    if (!templateDraft || event.target.dataset.blockField !== "type") return;
    const sectionNode = event.target.closest("[data-section-index]");
    const blockNode = event.target.closest("[data-block-index]");
    const block =
      templateDraft.definition.sections[Number(sectionNode.dataset.sectionIndex)].blocks[
        Number(blockNode.dataset.blockIndex)
      ];
    block.type = event.target.value;
    block.columns =
      block.type === "table" ? [{ id: templateId("column"), label: "列 1", instruction: "" }] : [];
    scheduleTemplatePersist();
    renderTemplateStructureEditor();
  });
  templateSectionsEditor.addEventListener("click", function (event) {
    if (!templateDraft) return;
    const sectionNode = event.target.closest("[data-section-index]");
    if (!sectionNode) return;
    const sectionIndex = Number(sectionNode.dataset.sectionIndex);
    const sections = templateDraft.definition.sections;
    const section = sections[sectionIndex];
    const blockNode = event.target.closest("[data-block-index]");
    const blockIndex = blockNode ? Number(blockNode.dataset.blockIndex) : -1;
    if (event.target.closest("[data-section-remove]")) {
      if (sections.length === 1) {
        toast("模板至少需要一个章节");
        return;
      }
      sections.splice(sectionIndex, 1);
    } else if (event.target.closest("[data-section-move]")) {
      moveArrayItem(
        sections,
        sectionIndex,
        event.target.closest("[data-section-move]").dataset.sectionMove === "up" ? -1 : 1
      );
    } else if (event.target.closest("[data-block-remove]")) {
      if (section.blocks.length === 1) {
        toast("每个章节至少需要一个内容块");
        return;
      }
      section.blocks.splice(blockIndex, 1);
    } else if (event.target.closest("[data-block-move]")) {
      moveArrayItem(
        section.blocks,
        blockIndex,
        event.target.closest("[data-block-move]").dataset.blockMove === "up" ? -1 : 1
      );
    } else if (event.target.closest("[data-block-add]")) {
      const selector = sectionNode.querySelector("[data-new-block-type]");
      section.blocks.push(newTemplateBlock(selector.value));
    } else if (event.target.closest("[data-column-add]")) {
      const block = section.blocks[blockIndex];
      if (block.columns.length >= 20) return;
      block.columns.push({
        id: templateId("column"),
        label: "列 " + (block.columns.length + 1),
        instruction: "",
      });
    } else if (event.target.closest("[data-column-remove]")) {
      const block = section.blocks[blockIndex];
      if (block.columns.length === 1) {
        toast("表格至少需要一列");
        return;
      }
      const columnNode = event.target.closest("[data-column-index]");
      block.columns.splice(Number(columnNode.dataset.columnIndex), 1);
    } else return;
    scheduleTemplatePersist();
    renderTemplateStructureEditor();
  });
  templateAiSend.addEventListener("click", reviseTemplateWithAi);
  templateAiInput.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      reviseTemplateWithAi();
    }
  });
  templateSaveBtn.addEventListener("click", openTemplateNameDialog);
  templateNameCancel.addEventListener("click", closeTemplateNameDialog);
  templateNameForm.addEventListener("submit", function (event) {
    event.preventDefault();
    saveNamedTemplate();
  });
  document.querySelectorAll("[data-template-pane]").forEach(function (button) {
    button.addEventListener("click", function () {
      document.querySelectorAll("[data-template-pane]").forEach(function (item) {
        item.classList.toggle("active", item === button);
      });
      const previewing = button.dataset.templatePane === "preview";
      templateEditorPane.classList.toggle("mobile-hidden", previewing);
      templatePreviewPane.classList.toggle("mobile-hidden", !previewing);
    });
  });
  if (deleteDataBtn) deleteDataBtn.addEventListener("click", deleteAllData);
  historyRefresh.addEventListener("click", loadHistory);
  const recWave = document.getElementById("rec-wave");
  const recTimer = document.getElementById("rec-timer");
  const recText = document.getElementById("rec-text");
  const recStatus = document.getElementById("rec-status");
  const recPause = document.getElementById("rec-pause");
  const recPlus = document.getElementById("rec-plus");
  const recDone = document.getElementById("rec-done");

  let recInterval = null;
  let recStartTime = 0;
  let isRecording = false;
  let isPaused = false;
  let recPausedAt = 0;
  let recPausedDuration = 0;
  let recEnding = false;
  let sendAfterRecording = false;
  let finalText = "";
  let endTimeout = null;

  let audioCtx = null;
  let audioStream = null;
  let processor = null;
  let analyser = null;
  let waveData = null;
  let waveFrame = null;
  let asrWs = null;

  function buildWave() {
    recWave.innerHTML = "";
    for (let i = 0; i < 56; i++) {
      const s = document.createElement("span");
      s.dataset.scale = "0.12";
      s.style.transform = "scaleY(.12)";
      recWave.appendChild(s);
    }
  }

  function renderLiveWave() {
    if (!isRecording) return;
    const bars = recWave.children;
    if (analyser && waveData && !isPaused) {
      analyser.getByteTimeDomainData(waveData);
      const step = waveData.length / bars.length;
      for (let i = 0; i < bars.length; i++) {
        const from = Math.floor(i * step);
        const to = Math.max(from + 1, Math.floor((i + 1) * step));
        let peak = 0;
        for (let j = from; j < to && j < waveData.length; j++) {
          peak = Math.max(peak, Math.abs(waveData[j] - 128) / 128);
        }
        const target = 0.12 + Math.min(1, peak * 5.2) * 0.88;
        const previous = Number(bars[i].dataset.scale || 0.12);
        const next = previous * 0.5 + target * 0.5;
        bars[i].dataset.scale = next.toFixed(3);
        bars[i].style.transform = "scaleY(" + next.toFixed(3) + ")";
      }
    } else {
      for (let i = 0; i < bars.length; i++) {
        const previous = Number(bars[i].dataset.scale || 0.12);
        const next = previous * 0.72 + 0.12 * 0.28;
        bars[i].dataset.scale = next.toFixed(3);
        bars[i].style.transform = "scaleY(" + next.toFixed(3) + ")";
      }
    }
    waveFrame = requestAnimationFrame(renderLiveWave);
  }

  function startWaveMeter() {
    if (waveFrame) cancelAnimationFrame(waveFrame);
    waveFrame = requestAnimationFrame(renderLiveWave);
  }

  function formatTime(sec) {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return (m < 10 ? "0" + m : m) + ":" + (s < 10 ? "0" + s : s);
  }

  function asrWsUrl() {
    const url = new URL("ws/asr", document.baseURI);
    url.protocol = location.protocol === "https:" ? "wss:" : "ws:";
    return url.toString();
  }

  function downsampleTo16k(input, fromRate) {
    const ratio = Math.max(1, fromRate / 16000);
    const outLen = Math.floor(input.length / ratio);
    const out = new Int16Array(outLen);
    for (let i = 0; i < outLen; i++) {
      let s = input[Math.floor(i * ratio)];
      if (s > 1) s = 1;
      else if (s < -1) s = -1;
      out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    return out;
  }

  function setupAudioProcessing() {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    audioCtx = new Ctx();
    if (audioCtx.resume) audioCtx.resume();
    const source = audioCtx.createMediaStreamSource(audioStream);
    analyser = audioCtx.createAnalyser();
    analyser.fftSize = 256;
    analyser.smoothingTimeConstant = 0.72;
    waveData = new Uint8Array(analyser.fftSize);
    processor = audioCtx.createScriptProcessor(4096, 1, 1);
    processor.onaudioprocess = function (e) {
      if (!isRecording || isPaused) return;
      if (!asrWs || asrWs.readyState !== WebSocket.OPEN) return;
      const pcm = downsampleTo16k(e.inputBuffer.getChannelData(0), audioCtx.sampleRate);
      asrWs.send(pcm.buffer);
    };
    source.connect(analyser);
    source.connect(processor);
    processor.connect(audioCtx.destination);
    if (isPaused && audioCtx.suspend) audioCtx.suspend();
  }

  function startRecording() {
    if (isRecording) return;
    isRecording = true;
    isPaused = false;
    recPausedAt = 0;
    recPausedDuration = 0;
    recEnding = false;
    sendAfterRecording = false;
    finalText = "";
    recStartTime = Date.now();
    recTimer.textContent = "00:00";
    recStatus.textContent = "正在录音";
    recText.textContent = "";
    recPause.disabled = false;
    recDone.disabled = false;
    recPause.setAttribute("aria-label", "暂停录音");
    buildWave();
    inputPanel.classList.add("recording");
    inputPanel.classList.remove("paused", "recording-ending");
    document.body.classList.add("composer-recording");
    startWaveMeter();
    recInterval = setInterval(function () {
      const pausedNow = isPaused ? Date.now() - recPausedAt : 0;
      const sec = Math.floor((Date.now() - recStartTime - recPausedDuration - pausedNow) / 1000);
      recTimer.textContent = formatTime(sec);
    }, 200);
    setupAsr();
  }

  async function setupAsr() {
    try {
      audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      toast("无法访问麦克风：请允许权限（需 HTTPS 或 localhost）");
      finishRecording(false, true);
      return;
    }
    try {
      setupAudioProcessing();
    } catch (e) {
      toast("音频处理初始化失败");
      finishRecording(false, true);
      return;
    }
    let ws;
    try {
      ws = new WebSocket(asrWsUrl());
    } catch (e) {
      toast("转写服务连接失败");
      finishRecording(false, true);
      return;
    }
    asrWs = ws;
    ws.binaryType = "arraybuffer";
    ws.onmessage = function (ev) {
      let data;
      try {
        data = JSON.parse(ev.data);
      } catch (e) {
        return;
      }
      if (data.type === "partial") {
        recText.textContent = data.text || "";
      } else if (data.type === "final") {
        finalText = (data.text || "").trim();
        if (finalText) recText.textContent = finalText;
        finishRecording(true);
      } else if (data.type === "error") {
        toast(data.message || "转写失败");
        finishRecording(false, true);
      }
    };
    ws.onerror = function () {
      toast("转写连接中断");
      finishRecording(false, true);
    };
  }

  function confirmRecording() {
    if (!isRecording || recEnding) return;
    recEnding = true;
    sendAfterRecording = true;
    inputPanel.classList.add("recording-ending");
    recStatus.textContent = "正在发送";
    recPause.disabled = true;
    recDone.disabled = true;
    try {
      if (asrWs && asrWs.readyState === WebSocket.OPEN) asrWs.send(JSON.stringify({ type: "end" }));
    } catch (e) {}
    endTimeout = setTimeout(function () {
      finishRecording(true);
    }, 6000);
  }

  function toggleRecordingPause() {
    if (!isRecording || recEnding) return;
    isPaused = !isPaused;
    inputPanel.classList.toggle("paused", isPaused);
    if (isPaused) {
      recPausedAt = Date.now();
      recStatus.textContent = "已暂停";
      recPause.setAttribute("aria-label", "继续录音");
      try {
        if (audioCtx && audioCtx.state === "running") audioCtx.suspend();
      } catch (e) {}
    } else {
      recPausedDuration += Date.now() - recPausedAt;
      recPausedAt = 0;
      recStatus.textContent = "正在录音";
      recPause.setAttribute("aria-label", "暂停录音");
      try {
        if (audioCtx && audioCtx.state === "suspended") audioCtx.resume();
      } catch (e) {}
    }
  }

  function finishRecording(useText, silent) {
    if (!isRecording) return;
    isRecording = false;
    recEnding = false;
    clearTimeout(endTimeout);
    clearInterval(recInterval);
    recInterval = null;
    if (waveFrame) cancelAnimationFrame(waveFrame);
    waveFrame = null;
    inputPanel.classList.remove("recording", "paused", "recording-ending");
    document.body.classList.remove("composer-recording");

    try {
      if (processor) {
        processor.disconnect();
      }
    } catch (e) {}
    try {
      if (audioCtx && audioCtx.state !== "closed") {
        audioCtx.close();
      }
    } catch (e) {}
    try {
      if (audioStream) {
        audioStream.getTracks().forEach(function (t) {
          t.stop();
        });
      }
    } catch (e) {}
    processor = null;
    analyser = null;
    waveData = null;
    audioCtx = null;
    audioStream = null;
    try {
      if (asrWs) {
        asrWs.onmessage = null;
        asrWs.close();
      }
    } catch (e) {}
    asrWs = null;

    const text = (finalText || recText.textContent || "").trim();
    const shouldSend = useText && sendAfterRecording && Boolean(text);
    if (silent) {
      // 不提示
    } else if (useText && text) {
      input.value = text;
      autoGrow();
      syncSend();
      toast("转写完成");
    } else if (useText) {
      toast("没有识别到内容");
    } else {
      toast("已取消录音");
    }
    finalText = "";
    sendAfterRecording = false;
    isPaused = false;
    recPausedAt = 0;
    recPausedDuration = 0;
    if (shouldSend) sendMessage();
  }

  micBtn.addEventListener("click", function () {
    if (isRecording) return;
    startRecording();
  });
  plusBtn.addEventListener("click", openUploadMenu);
  uploadMenuBackdrop.addEventListener("click", closeUploadMenu);
  uploadMenu.addEventListener("click", function (e) {
    const option = e.target.closest("[data-upload-accept]");
    if (!option) return;
    fileInput.accept = option.dataset.uploadAccept || "";
    fileInput.click();
    closeUploadMenu();
  });
  fileInput.addEventListener("change", function () {
    handleFiles(fileInput.files);
    fileInput.value = "";
  });

  function eventHasFiles(e) {
    return Boolean(
      e.dataTransfer && Array.from(e.dataTransfer.types || []).indexOf("Files") !== -1
    );
  }

  document.addEventListener("dragenter", function (e) {
    if (!eventHasFiles(e) || !window.matchMedia("(hover: hover) and (pointer: fine)").matches)
      return;
    e.preventDefault();
    if (document.body.classList.contains("template-workspace-open")) return;
    dragDepth += 1;
    if (settingsState && settingsState.configured && !isStreaming) dropOverlay.hidden = false;
  });
  document.addEventListener("dragover", function (e) {
    if (!eventHasFiles(e)) return;
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
  });
  document.addEventListener("dragleave", function (e) {
    if (!eventHasFiles(e)) return;
    dragDepth = Math.max(0, dragDepth - 1);
    if (!dragDepth) dropOverlay.hidden = true;
  });
  document.addEventListener("drop", function (e) {
    if (!eventHasFiles(e)) return;
    e.preventDefault();
    dragDepth = 0;
    dropOverlay.hidden = true;
    if (document.body.classList.contains("template-workspace-open")) return;
    if (!(settingsState && settingsState.configured) || isStreaming) return;
    handleFiles(e.dataTransfer.files);
  });

  function closeModeMenu() {
    modeMenu.hidden = true;
    modeBtn.setAttribute("aria-expanded", "false");
  }

  modeBtn.addEventListener("click", function () {
    const willOpen = modeMenu.hidden;
    modeMenu.hidden = !willOpen;
    modeBtn.setAttribute("aria-expanded", String(willOpen));
  });
  modeMenu.addEventListener("click", function (e) {
    const option = e.target.closest("[data-mode]");
    if (!option) return;
    chatMode = option.dataset.mode || "advanced";
    modeLabel.textContent = chatMode === "normal" ? "普通" : "高级";
    modeMenu.querySelectorAll("[data-mode]").forEach(function (item) {
      item.setAttribute("aria-selected", String(item === option));
    });
    closeModeMenu();
    input.focus();
  });
  document.addEventListener("click", function (e) {
    if (!e.target.closest("#mode-picker")) closeModeMenu();
    if (!e.target.closest("#composer-shell")) closeUploadMenu();
  });
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    if (!quotaDialogBackdrop.hidden) {
      e.preventDefault();
      closeQuotaDialog();
      return;
    }
    closeModeMenu();
    closeUploadMenu();
    dropOverlay.hidden = true;
    dragDepth = 0;
    if (drawer.classList.contains("open")) closeDrawer();
  });
  quotaDialogClose.addEventListener("click", closeQuotaDialog);
  quotaDialogBackdrop.addEventListener("click", function (e) {
    if (e.target === quotaDialogBackdrop) closeQuotaDialog();
  });
  quotaDialog.addEventListener("keydown", function (e) {
    if (e.key !== "Tab") return;
    e.preventDefault();
    quotaDialogClose.focus();
  });
  recPause.addEventListener("click", toggleRecordingPause);
  recPlus.addEventListener("click", function () {
    toast("请先结束录音，再添加附件");
  });
  recDone.addEventListener("click", confirmRecording);
  sendBtn.addEventListener("click", function (e) {
    e.preventDefault();
    if (!sendBtn.disabled) sendMessage();
  });
  settingsForm.addEventListener("submit", function (e) {
    e.preventDefault();
    if (
      settingsState &&
      settingsState.configured &&
      hasUnarchivedContent() &&
      !window.confirm("保存设置会开始新会话并清空尚未归档的内容，继续吗？")
    )
      return;
    saveSettings();
  });
  weekOneInput.addEventListener("change", function () {
    const aligned = mondayFromValue(weekOneInput.value);
    if (aligned) weekOneInput.value = aligned;
  });
  input.addEventListener("input", function () {
    autoGrow();
    syncSend();
  });
  input.addEventListener("compositionend", function () {
    autoGrow();
    syncSend();
  });
  input.addEventListener("paste", function () {
    setTimeout(function () {
      autoGrow();
      syncSend();
    }, 0);
  });
  input.addEventListener("keydown", function (e) {
    if (e.isComposing || e.keyCode === 229) return;
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  autoGrow();
  syncSend();
  document.body.classList.add("booting");
  loadSettings();
  loadPrivacy();
})();
