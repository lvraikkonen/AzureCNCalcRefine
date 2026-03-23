/**
 * Admin SPA — Alpine.js router + top-level app state.
 *
 * Routes (hash-based):
 *   #/            → dashboard
 *   #/configs     → config list
 *   #/configs/new → new config editor
 *   #/configs/:name → config editor
 *   #/history/:name → version history
 *   #/catalog     → catalog manager
 *   #/import      → bulk import
 *   #/login       → login (only shown if ADMIN_TOKEN required)
 */

import { configList } from "./components/config-list.js";
import { configEditor } from "./components/config-editor.js";
import { versionHistory } from "./components/version-history.js";
import { catalogManager } from "./components/catalog-manager.js";
import * as api from "./api.js";

// Make component factories available globally for Alpine x-data
window.configList = configList;
window.configEditor = configEditor;
window.versionHistory = versionHistory;
window.catalogManager = catalogManager;

// ── Router ────────────────────────────────────────────────────────────────────

function parseRoute(hash) {
  const path = hash.replace(/^#/, "") || "/";
  const parts = path.split("/").filter(Boolean);

  if (parts.length === 0) return { view: "dashboard", param: null };
  if (parts[0] === "configs") {
    if (parts[1] === "new") return { view: "config-editor-new", param: null };
    if (parts[1]) return { view: "config-editor", param: decodeURIComponent(parts[1]) };
    return { view: "config-list", param: null };
  }
  if (parts[0] === "history" && parts[1]) {
    return { view: "version-history", param: decodeURIComponent(parts[1]) };
  }
  if (parts[0] === "catalog") return { view: "catalog", param: null };
  if (parts[0] === "import") return { view: "import", param: null };
  if (parts[0] === "login") return { view: "login", param: null };
  return { view: "dashboard", param: null };
}

// ── Dashboard data ────────────────────────────────────────────────────────────

async function dashboardData() {
  const configs = await api.listConfigs({ limit: 500 });
  return {
    total: configs.length,
    published: configs.filter((c) => c.status === "published").length,
    draft: configs.filter((c) => c.status === "draft").length,
    archived: configs.filter((c) => c.status === "archived").length,
    recent: [...configs]
      .sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at))
      .slice(0, 5),
  };
}

// ── Import page ───────────────────────────────────────────────────────────────

window.importPage = function () {
  return {
    running: false,
    result: null,
    error: null,
    overwrite: false,

    async runImport() {
      if (
        !confirm(
          `从 JSON 文件导入${this.overwrite ? "（覆盖已有记录）" : ""}？确认后将写入数据库。`
        )
      )
        return;
      this.running = true;
      this.result = null;
      this.error = null;
      try {
        this.result = await api.importJsonFiles(this.overwrite);
      } catch (e) {
        this.error = e.message;
      } finally {
        this.running = false;
      }
    },
  };
};

// ── Login page ────────────────────────────────────────────────────────────────

window.loginPage = function () {
  return {
    token: "",
    error: null,

    submit() {
      if (!this.token.trim()) { this.error = "请输入 Admin Token"; return; }
      sessionStorage.setItem("admin_token", this.token.trim());
      window.location.hash = "#/";
    },
  };
};

// ── Alpine app root ───────────────────────────────────────────────────────────

window.adminApp = function () {
  return {
    route: { view: "dashboard", param: null },
    dashboard: null,
    dashboardLoading: false,

    init() {
      this._navigate();
      window.addEventListener("hashchange", () => this._navigate());
    },

    async _navigate() {
      this.route = parseRoute(window.location.hash);
      if (this.route.view === "dashboard") {
        this.dashboardLoading = true;
        try {
          this.dashboard = await dashboardData();
        } catch (_) {
          this.dashboard = null;
        } finally {
          this.dashboardLoading = false;
        }
      }
    },

    navigate(hash) {
      window.location.hash = hash;
    },

    formatDate(iso) {
      if (!iso) return "—";
      return new Date(iso).toLocaleString("zh-CN", { hour12: false });
    },

    statusBadgeClass(status) {
      return {
        draft: "bg-yellow-100 text-yellow-800",
        published: "bg-green-100 text-green-800",
        archived: "bg-gray-100 text-gray-500",
      }[status] ?? "bg-gray-100 text-gray-500";
    },
  };
};
