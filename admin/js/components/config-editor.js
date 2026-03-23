/**
 * Config Editor component — form + JSON dual-panel editor for service configs.
 *
 * Usage (Alpine.js x-data):
 *   <div x-data="configEditor('Virtual Machines')"> ... </div>
 */

import * as api from "../api.js";

const QUANTITY_MODELS = ["instances_x_hours", "per_meter"];

export function configEditor(serviceName) {
  return {
    serviceName,
    isNew: !serviceName,
    config: null,           // raw ServiceConfigResponse from API
    jsonText: "{}",         // text in the JSON editor panel
    jsonError: null,        // parse error from the JSON panel
    formData: {             // mirrors the most-used fields for the form panel
      service_name: "",
      api_service_name: "",
      quantity_model: "instances_x_hours",
      quantity_label: "VMs",
      hours_per_month: 730,
      dimension_labels: "{}",
      hidden_dimensions: "",
    },
    activePanel: "form",    // "form" | "json"
    loading: false,
    saving: false,
    publishing: false,
    validation: null,       // ValidationResult
    error: null,
    successMsg: null,
    changedBy: "",
    changeSummary: "",

    // ── Lifecycle ────────────────────────────────────────────────────────────

    async init() {
      if (!this.isNew) {
        await this.load();
      } else {
        this.jsonText = JSON.stringify(this._defaultConfig(), null, 2);
        this._syncJsonToForm();
      }
    },

    _defaultConfig() {
      return {
        service_name: "",
        quantity_model: "instances_x_hours",
        quantity_label: "VMs",
        defaults: {
          hours_per_month: 730,
          selections: {},
          sub_selections: {},
        },
        dimension_labels: {},
        hidden_dimensions: [],
      };
    },

    async load() {
      this.loading = true;
      this.error = null;
      try {
        this.config = await api.getConfig(this.serviceName);
        this.jsonText = JSON.stringify(this.config.config, null, 2);
        this._syncJsonToForm();
      } catch (e) {
        this.error = e.message;
      } finally {
        this.loading = false;
      }
    },

    // ── Panel switching ──────────────────────────────────────────────────────

    switchToJson() {
      // Sync form → JSON before switching
      this._syncFormToJson();
      this.activePanel = "json";
    },

    switchToForm() {
      // Parse JSON → form before switching
      if (!this._parseJson()) return;
      this._syncJsonToForm();
      this.activePanel = "form";
    },

    // ── Form ↔ JSON sync ─────────────────────────────────────────────────────

    _parseJson() {
      try {
        JSON.parse(this.jsonText);
        this.jsonError = null;
        return true;
      } catch (e) {
        this.jsonError = e.message;
        return false;
      }
    },

    _syncFormToJson() {
      try {
        const parsed = JSON.parse(this.jsonText);
        // Apply form fields back onto the parsed config
        if (this.isNew || !parsed.service_name) {
          parsed.service_name = this.formData.service_name;
        }
        parsed.api_service_name = this.formData.api_service_name || undefined;
        parsed.quantity_model = this.formData.quantity_model;
        parsed.quantity_label = this.formData.quantity_label;
        if (!parsed.defaults) parsed.defaults = {};
        parsed.defaults.hours_per_month = Number(this.formData.hours_per_month) || 730;
        try {
          parsed.dimension_labels = JSON.parse(this.formData.dimension_labels || "{}");
        } catch (_) {}
        parsed.hidden_dimensions = this.formData.hidden_dimensions
          ? this.formData.hidden_dimensions.split(",").map((s) => s.trim()).filter(Boolean)
          : [];
        this.jsonText = JSON.stringify(parsed, null, 2);
        this.jsonError = null;
      } catch (e) {
        this.jsonError = e.message;
      }
    },

    _syncJsonToForm() {
      try {
        const parsed = JSON.parse(this.jsonText);
        this.formData.service_name = parsed.service_name || "";
        this.formData.api_service_name = parsed.api_service_name || "";
        this.formData.quantity_model = parsed.quantity_model || "instances_x_hours";
        this.formData.quantity_label = parsed.quantity_label || "VMs";
        this.formData.hours_per_month = parsed.defaults?.hours_per_month ?? 730;
        this.formData.dimension_labels = JSON.stringify(parsed.dimension_labels ?? {}, null, 2);
        const hd = parsed.hidden_dimensions;
        this.formData.hidden_dimensions = Array.isArray(hd) ? hd.join(", ") : "";
        this.jsonError = null;
      } catch (_) {}
    },

    _currentConfig() {
      this._syncFormToJson();
      try {
        return JSON.parse(this.jsonText);
      } catch (_) {
        return null;
      }
    },

    // ── Validate ─────────────────────────────────────────────────────────────

    async validate() {
      const cfg = this._currentConfig();
      if (!cfg) return;
      const sn = this.serviceName || cfg.service_name || "_validate";
      try {
        this.validation = await api.validateConfig(sn, cfg);
      } catch (e) {
        this.error = e.message;
      }
    },

    // ── Save ─────────────────────────────────────────────────────────────────

    async save() {
      const cfg = this._currentConfig();
      if (!cfg) { this.error = "JSON 格式有误，请修正后再保存"; return; }

      this.saving = true;
      this.error = null;
      this.successMsg = null;
      try {
        if (this.isNew) {
          const res = await api.createConfig({
            service_name: cfg.service_name || this.formData.service_name,
            config: cfg,
            changed_by: this.changedBy || null,
          });
          this.isNew = false;
          this.serviceName = res.service_name;
          this.config = res;
          this.successMsg = "配置已创建（草稿状态）";
          window.location.hash = `#/configs/${encodeURIComponent(res.service_name)}`;
        } else {
          this.config = await api.updateConfig(this.serviceName, {
            config: cfg,
            changed_by: this.changedBy || null,
            change_summary: this.changeSummary || null,
          });
          this.jsonText = JSON.stringify(this.config.config, null, 2);
          this.successMsg = "配置已保存（草稿状态）";
        }
        this.validation = null;
      } catch (e) {
        this.error = e.message;
      } finally {
        this.saving = false;
      }
    },

    // ── Publish ──────────────────────────────────────────────────────────────

    async publish() {
      if (!confirm(`发布 "${this.serviceName}" 的配置？发布后立即对外生效。`)) return;
      this.publishing = true;
      this.error = null;
      this.successMsg = null;
      try {
        this.config = await api.publishConfig(this.serviceName, {
          changed_by: this.changedBy || null,
        });
        this.successMsg = "配置已发布！Explore API 将立即使用新配置。";
      } catch (e) {
        this.error = e.message;
      } finally {
        this.publishing = false;
      }
    },

    // ── Helpers ──────────────────────────────────────────────────────────────

    get quantityModels() { return QUANTITY_MODELS; },

    statusBadgeClass(status) {
      return {
        draft: "bg-yellow-100 text-yellow-800",
        published: "bg-green-100 text-green-800",
        archived: "bg-gray-100 text-gray-500",
      }[status] ?? "bg-gray-100 text-gray-500";
    },

    formatDate(iso) {
      if (!iso) return "—";
      return new Date(iso).toLocaleString("zh-CN", { hour12: false });
    },

    navigate(hash) {
      window.location.hash = hash;
    },
  };
}
