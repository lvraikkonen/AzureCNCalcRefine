/**
 * Version History component — shows config change history with revert support.
 */

import * as api from "../api.js";

export function versionHistory(serviceName) {
  return {
    serviceName,
    history: [],
    loading: false,
    error: null,
    selectedVersion: null,
    reverting: false,
    changedBy: "",

    async init() {
      await this.load();
    },

    async load() {
      this.loading = true;
      this.error = null;
      try {
        this.history = await api.getConfigHistory(this.serviceName);
      } catch (e) {
        this.error = e.message;
      } finally {
        this.loading = false;
      }
    },

    selectVersion(entry) {
      this.selectedVersion = this.selectedVersion?.version === entry.version ? null : entry;
    },

    async revert(version) {
      if (!confirm(`确定要回退到版本 ${version} 吗？这将创建一个新的草稿版本。`)) return;
      this.reverting = true;
      this.error = null;
      try {
        await api.revertConfig(this.serviceName, version, { changed_by: this.changedBy || null });
        await this.load();
        alert(`已成功回退到版本 ${version}（新草稿已创建，请发布以生效）`);
      } catch (e) {
        this.error = e.message;
      } finally {
        this.reverting = false;
      }
    },

    formatDate(iso) {
      if (!iso) return "—";
      return new Date(iso).toLocaleString("zh-CN", { hour12: false });
    },

    formatJson(obj) {
      return JSON.stringify(obj, null, 2);
    },

    navigate(hash) {
      window.location.hash = hash;
    },
  };
}
