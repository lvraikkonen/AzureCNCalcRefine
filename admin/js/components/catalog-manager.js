/**
 * Catalog Manager component — manage product families and services.
 */

import * as api from "../api.js";

export function catalogManager() {
  return {
    families: [],
    loading: false,
    error: null,
    successMsg: null,
    // New family form
    newFamily: { key: "", label: "", order: 0 },
    showNewFamily: false,
    // New service form
    newService: {
      family_key: "",
      service_name: "",
      description: "",
      icon: "",
      popular: false,
      order: 0,
    },
    showNewService: false,
    addingFamily: false,
    addingService: false,
    deletingKey: null,

    async init() {
      await this.load();
    },

    async load() {
      this.loading = true;
      this.error = null;
      try {
        this.families = await api.listFamilies();
      } catch (e) {
        this.error = e.message;
      } finally {
        this.loading = false;
      }
    },

    async addFamily() {
      if (!this.newFamily.key || !this.newFamily.label) {
        this.error = "Family key 和 label 不能为空";
        return;
      }
      this.addingFamily = true;
      this.error = null;
      try {
        await api.createFamily(this.newFamily);
        this.newFamily = { key: "", label: "", order: 0 };
        this.showNewFamily = false;
        this.successMsg = "Family 已创建";
        await this.load();
      } catch (e) {
        this.error = e.message;
      } finally {
        this.addingFamily = false;
      }
    },

    async deleteFamily(key) {
      if (!confirm(`删除 family "${key}"？只有空 family（无服务）才能删除。`)) return;
      this.deletingKey = key;
      this.error = null;
      try {
        await api.deleteFamily(key);
        this.successMsg = `Family "${key}" 已删除`;
        await this.load();
      } catch (e) {
        this.error = e.message;
      } finally {
        this.deletingKey = null;
      }
    },

    async addService() {
      if (!this.newService.family_key || !this.newService.service_name) {
        this.error = "Family 和 service name 不能为空";
        return;
      }
      this.addingService = true;
      this.error = null;
      try {
        await api.createServiceEntry({
          ...this.newService,
          icon: this.newService.icon || null,
        });
        this.newService = { family_key: "", service_name: "", description: "", icon: "", popular: false, order: 0 };
        this.showNewService = false;
        this.successMsg = "服务已添加到目录";
        await this.load();
      } catch (e) {
        this.error = e.message;
      } finally {
        this.addingService = false;
      }
    },

    async deleteService(serviceName) {
      if (!confirm(`从目录移除 "${serviceName}"？`)) return;
      this.deletingKey = serviceName;
      this.error = null;
      try {
        await api.deleteServiceEntry(serviceName);
        this.successMsg = `"${serviceName}" 已从目录移除`;
        await this.load();
      } catch (e) {
        this.error = e.message;
      } finally {
        this.deletingKey = null;
      }
    },
  };
}
