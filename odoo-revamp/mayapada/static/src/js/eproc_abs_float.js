/** @odoo-module **/

import { registry } from "@web/core/registry";
import { formatFloat } from "@web/views/fields/formatters";
import { FloatField } from "@web/views/fields/float/float_field";

export class EprocAbsFloatField extends FloatField {
    get formattedValue() {
        const value = this.props.value;
        if (value === false || value === undefined || value === null) {
            return super.formattedValue;
        }
        return formatFloat(Math.abs(value), {
            digits: this.props.digits,
        });
    }
}

registry.category("fields").add("eproc_abs_float", EprocAbsFloatField);
