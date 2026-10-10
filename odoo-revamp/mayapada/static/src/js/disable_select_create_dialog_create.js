/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { X2ManyField } from "@web/views/fields/x2many/x2many_field";

function shouldDisableCreate(field) {
    const context = field.props.record.getFieldContext(field.props.name);
    return Boolean(context && context.disable_create_in_select_dialog);
}

patch(X2ManyField.prototype, "mayapada.disable_select_create_dialog_create", {
    async onAdd() {
        if (!shouldDisableCreate(this)) {
            return this._super.apply(this, arguments);
        }
        const previousCreate = this.activeActions.create;
        const previousCreateEdit = this.activeActions.createEdit;
        this.activeActions.create = false;
        this.activeActions.createEdit = false;
        try {
            return await this._super.apply(this, arguments);
        } finally {
            this.activeActions.create = previousCreate;
            this.activeActions.createEdit = previousCreateEdit;
        }
    },
});
