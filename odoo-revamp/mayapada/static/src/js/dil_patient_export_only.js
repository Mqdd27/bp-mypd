/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ListController } from "@web/views/list/list_controller";

function isDilExportOnly(controller) {
    const context = controller.props.context || {};
    return Boolean(
        context.dil_patient_export_only ||
            context.dil_doctor_external_export_only ||
            context.dil_doctor_internal_export_only
    );
}

function keepExportOnly(actionMenuItems) {
    const exportItems = [];
    const filteredMenuItems = {};

    for (const [category, items] of Object.entries(actionMenuItems || {})) {
        if (!Array.isArray(items)) {
            filteredMenuItems[category] = items;
            continue;
        }
        exportItems.push(...items.filter((item) => item && item.key === "export"));
        filteredMenuItems[category] = [];
    }

    filteredMenuItems.other = exportItems;

    return filteredMenuItems;
}

patch(ListController.prototype, "mayapada.dil_patient_export_only", {
    getActionMenuItems() {
        const actionMenuItems = this._super.apply(this, arguments);
        if (!isDilExportOnly(this)) {
            return actionMenuItems;
        }
        return keepExportOnly(actionMenuItems);
    },
});
