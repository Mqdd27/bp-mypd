/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ListController } from "@web/views/list/list_controller";

const LIST_VIEW_ACTIONS = {
    "eproc.orderpoint": {
        importAction: "mayapada.action_erp_pmm_orderpoint_import_wizard",
        importLabel: "Import",
    },

    "tariff.pricelist": {
        action: "mayapada.action_acc_tariff_pricelist_wizard",
        label: "Open Pricelist Wizard",
        exportAction: "mayapada.action_acc_tariff_pricelist_existing_export_wizard",
        exportLabel: "Export Pricelist",
        importAction: "mayapada.action_acc_tariff_pricelist_import_wizard",
        importLabel: "Import Pricelist",
    },

    "tariff.dependency": {
        action: "mayapada.action_acc_tariff_dependency_wizard",
        label: "Open Dependency Wizard",
        exportAction: "mayapada.action_acc_tariff_dependency_existing_export_wizard",
        exportLabel: "Export Dependency",
        importAction: "mayapada.action_acc_tariff_dependency_import_wizard",
        importLabel: "Import Dependency",
    },

    "tariff.markup": {
        action: "mayapada.action_acc_tariff_markup_wizard",
        label: "Open Markup Wizard",
        exportAction: "mayapada.action_acc_tariff_markup_existing_export_wizard",
        exportLabel: "Export Markup",
        importAction: "mayapada.action_acc_tariff_markup_import_wizard",
        importLabel: "Import Markup",
    },

    "tariff.pricelist.fixed": {
        action: "mayapada.action_acc_tariff_selling_price_wizard",
        label: "Open Fixed Price Wizard",

        exportAction: "mayapada.action_acc_tariff_selling_price_export_wizard",
        exportLabel: "Export Tariff",
    },

    "tariff.aggregation": {
        action: "mayapada.action_acc_tariff_aggregation_wizard",
        label: "Open Aggregation Wizard",
    },
};

patch(ListController.prototype, "mayapada.list_view_action_buttons", {

    getListViewActionConfig() {
        return LIST_VIEW_ACTIONS[
            this.model.root.resModel
        ];
    },

    // =========================================================
    // OPEN WIZARD
    // =========================================================

    hasListViewWizardButton() {
        const config = this.getListViewActionConfig();

        return Boolean(config && config.action);
    },

    getListViewWizardLabel() {
        const config = this.getListViewActionConfig();

        return config ? config.label : "Open Wizard";
    },

    async onOpenListViewWizard() {
        const config = this.getListViewActionConfig();

        if (config && config.action) {
            await this.actionService.doAction(config.action);
        }
    },

    // =========================================================
    // IMPORT
    // =========================================================

    hasListViewImportButton() {
        const config = this.getListViewActionConfig();
        return Boolean(config && config.importAction);
    },

    getListViewImportLabel() {
        const config = this.getListViewActionConfig();
        return config ? config.importLabel : "Import Data";
    },

    async onOpenListViewImport() {
        const config = this.getListViewActionConfig();
        if (config && config.importAction) {
            await this.actionService.doAction(config.importAction);
        }
    },

    // =========================================================
    // EXPORT
    // =========================================================

    hasListViewExportButton() {
        const config = this.getListViewActionConfig();
        return Boolean(config && config.exportAction);
    },

    getListViewExportLabel() {
        const config = this.getListViewActionConfig();
        return config ? config.exportLabel : "Export";
    },

    async onOpenListViewExport() {
        const config = this.getListViewActionConfig();
        if (config && config.exportAction) {
            const selectedIds = await this.getSelectedResIds();
            await this.actionService.doAction(config.exportAction, {
                additionalContext: {
                    active_model: this.model.root.resModel,
                    active_ids: selectedIds,
                },
            });
        }
    },
});
