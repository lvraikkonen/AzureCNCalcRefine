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
    activePanel: "form",    // "form" | "json" | "api-preview"
    loading: false,
    saving: false,
    publishing: false,
    validation: null,       // ValidationResult
    error: null,
    successMsg: null,
    changedBy: "",
    changeSummary: "",

    // API Preview state
    preview: {
      dataSource: "global",       // "cn" | "global"
      region: "eastus",
      cascadeLoading: false,
      cascadeResult: null,        // CascadeResponse
      cascadeError: null,
      metersLoading: false,
      metersResult: null,         // MetersResponse
      metersError: null,
    },

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

    switchToApiPreview() {
      // Sync form → JSON to ensure current config is up-to-date
      if (this.activePanel === "form") this._syncFormToJson();
      this.activePanel = "api-preview";
      // Pre-fill region from config defaults
      const cfg = this._currentConfig();
      if (cfg?.defaults?.selections?.armRegionName) {
        this.preview.region = cfg.defaults.selections.armRegionName;
        // Auto-detect data source from region
        this.preview.dataSource = this.preview.region.startsWith("china") ? "cn" : "global";
      }
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

    // ── API Preview ─────────────────────────────────────────────────────────

    _previewServiceName() {
      const cfg = this._currentConfig();
      return cfg?.api_service_name || cfg?.service_name || this.serviceName || "";
    },

    async previewCascade() {
      const sn = this._previewServiceName();
      if (!sn) return;
      this.preview.cascadeLoading = true;
      this.preview.cascadeError = null;
      this.preview.cascadeResult = null;
      this.preview.metersResult = null;
      try {
        const body = {
          service_name: sn,
          selections: {},
          data_source: this.preview.dataSource,
        };
        if (this.preview.region) {
          body.selections.armRegionName = this.preview.region;
        }
        this.preview.cascadeResult = await api.exploreCascade(body);
      } catch (e) {
        this.preview.cascadeError = e.message;
      } finally {
        this.preview.cascadeLoading = false;
      }
    },

    async previewCascadeWithSelections() {
      const sn = this._previewServiceName();
      if (!sn || !this.preview.cascadeResult) return;
      this.preview.cascadeLoading = true;
      this.preview.cascadeError = null;
      try {
        const selections = {};
        for (const dim of this.preview.cascadeResult.dimensions) {
          if (dim.selected) selections[dim.field] = dim.selected;
        }
        this.preview.cascadeResult = await api.exploreCascade({
          service_name: sn,
          selections,
          data_source: this.preview.dataSource,
        });
      } catch (e) {
        this.preview.cascadeError = e.message;
      } finally {
        this.preview.cascadeLoading = false;
      }
    },

    async previewMeters() {
      const sn = this._previewServiceName();
      if (!sn || !this.preview.cascadeResult) return;
      this.preview.metersLoading = true;
      this.preview.metersError = null;
      this.preview.metersResult = null;
      try {
        const dims = this.preview.cascadeResult.dimensions;
        const sel = (field) => dims.find((d) => d.field === field)?.selected;
        this.preview.metersResult = await api.exploreMeters({
          service_name: sn,
          region: sel("armRegionName"),
          product: sel("productName"),
          sku: sel("skuName"),
          data_source: this.preview.dataSource,
        });
      } catch (e) {
        this.preview.metersError = e.message;
      } finally {
        this.preview.metersLoading = false;
      }
    },

    previewMeterNames() {
      if (!this.preview.metersResult?.groups) return [];
      const names = [];
      for (const g of this.preview.metersResult.groups) {
        if (!names.includes(g.meter)) names.push(g.meter);
      }
      return names;
    },

    previewSuggestedMeterLabels() {
      const names = this.previewMeterNames();
      if (!names.length) return "";
      const obj = {};
      for (const n of names) obj[n] = n;
      return JSON.stringify(obj, null, 2);
    },

    previewSuggestedMeterOrder() {
      const names = this.previewMeterNames();
      if (!names.length) return "";
      return JSON.stringify(names, null, 2);
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
