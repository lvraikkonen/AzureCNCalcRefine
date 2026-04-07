/**
 * Config List component — shows all service configurations in a searchable table.
 *
 * Usage (Alpine.js x-data):
 *   <div x-data="configList()"> ... </div>
 */

import * as api from "../api.js";

export function configList() {
  return {
    configs: [],
    loading: false,
    error: null,
    search: "",
    statusFilter: "",
    actionLoading: null,

    // Template import modal state
    showTemplateModal: false,
    templates: [],
    templatesLoading: false,
    importingSlug: null,

    get filtered() {
      const q = this.search.toLowerCase();
      return this.configs.filter((c) => {
        const matchSearch = !q || c.service_name.toLowerCase().includes(q);
        const matchStatus = !this.statusFilter || c.status === this.statusFilter;
        return matchSearch && matchStatus;
      });
    },

    async init() {
      await this.load();
    },

    async load() {
      this.loading = true;
      this.error = null;
      try {
        this.configs = await api.listConfigs({ limit: 500 });
      } catch (e) {
        this.error = e.message;
      } finally {
        this.loading = false;
      }
    },

    async publish(serviceName) {
      if (!confirm(`发布 "${serviceName}" 的配置？发布后将立即对外生效。`)) return;
      this.actionLoading = serviceName;
      try {
        await api.publishConfig(serviceName);
        await this.load();
      } catch (e) {
        alert("发布失败: " + e.message);
      } finally {
        this.actionLoading = null;
      }
    },

    async archive(serviceName) {
      if (!confirm(`归档 "${serviceName}"？归档后将从列表隐藏（可筛选查看）。`)) return;
      this.actionLoading = serviceName;
      try {
        await api.archiveConfig(serviceName);
        await this.load();
      } catch (e) {
        alert("归档失败: " + e.message);
      } finally {
        this.actionLoading = null;
      }
    },

    async openTemplateModal() {
      this.showTemplateModal = true;
      this.templatesLoading = true;
      try {
        this.templates = await api.listTemplates();
      } catch (e) {
        alert("加载模板失败: " + e.message);
        this.showTemplateModal = false;
      } finally {
        this.templatesLoading = false;
      }
    },

    async importTemplate(slug) {
      this.importingSlug = slug;
      try {
        const result = await api.importTemplate(slug);
        if (result.action === "created") {
          // Refresh template list to update already_imported flags
          this.templates = await api.listTemplates();
          await this.load();
        } else {
          alert(`跳过: ${result.detail}`);
        }
      } catch (e) {
        alert("导入失败: " + e.message);
      } finally {
        this.importingSlug = null;
      }
    },

    async importAllTemplates() {
      const available = this.templates.filter((t) => !t.already_imported);
      if (!available.length) return;
      if (!confirm(`批量导入 ${available.length} 个模板？`)) return;
      for (const t of available) {
        await this.importTemplate(t.slug);
      }
    },

    navigate(hash) {
      window.location.hash = hash;
    },

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
  };
}
