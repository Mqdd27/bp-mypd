/** @odoo-module **/

import { onWillUpdateProps } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { evalDomain } from "@web/views/utils";
import { ListRenderer } from "@web/views/list/list_renderer";

const OPTIONAL_DEFAULTS_ATTRIBUTE = "optional_defaults";

/**
 * Each rule has an Odoo domain evaluated against the relational list's eval
 * context, and a value of "show" or "hide". The first matching rule wins.
 * Optional Columns choices are stored separately for each matched rule set.
 */
function optionalDefaultsConfig(column) {
    const rawValue = column.rawAttrs && column.rawAttrs[OPTIONAL_DEFAULTS_ATTRIBUTE];
    if (!rawValue) {
        return null;
    }
    try {
        const config = JSON.parse(rawValue);
        if (
            !Array.isArray(config.rules) ||
            !["show", "hide"].includes(config.default) ||
            config.rules.some(
                (rule) =>
                    !Array.isArray(rule.domain) ||
                    !["show", "hide"].includes(rule.value)
            )
        ) {
            throw new Error("Expected rules with domain/value and a show/hide default");
        }
        return config;
    } catch (error) {
        console.warn("Invalid optional_defaults on list field", column.name, error);
        return null;
    }
}

function resolveOptionalDefault(config, evalContext) {
    for (let index = 0; index < config.rules.length; index++) {
        const rule = config.rules[index];
        try {
            if (evalDomain(rule.domain, evalContext)) {
                return {
                    value: rule.value,
                    conditionKey: rule.key || `rule:${JSON.stringify(rule.domain)}`,
                };
            }
        } catch (error) {
            console.warn("Invalid optional_defaults domain", rule.domain, error);
        }
    }
    return { value: config.default, conditionKey: "default" };
}

function hasOptionalDefaults(columns) {
    return columns.some((column) => optionalDefaultsConfig(column));
}

function optionalDefaultsConditionKey(columns, evalContext) {
    const entries = columns
        .map((column) => {
            const config = optionalDefaultsConfig(column);
            if (!config) {
                return null;
            }
            return [
                column.name,
                resolveOptionalDefault(config, evalContext).conditionKey,
            ];
        })
        .filter(Boolean);
    return entries.length ? JSON.stringify(entries) : null;
}

function applyOptionalDefaults(columns, evalContext) {
    return columns.map((column) => {
        const config = optionalDefaultsConfig(column);
        if (!config) {
            return column;
        }
        const { value } = resolveOptionalDefault(config, evalContext);
        return { ...column, optional: value };
    });
}

patch(ListRenderer.prototype, "mayapada.optional_column_defaults", {
    setup() {
        this._super(...arguments);
        onWillUpdateProps((nextProps) => {
            if (!hasOptionalDefaults(nextProps.archInfo.columns)) {
                return;
            }
            const nextConditionKey = optionalDefaultsConditionKey(
                nextProps.archInfo.columns,
                nextProps.list.evalContext
            );
            if (nextConditionKey === null || nextConditionKey === this.optionalDefaultsConditionKey) {
                return;
            }
            this.optionalDefaultsConditionKey = nextConditionKey;
            this.allColumns = applyOptionalDefaults(
                nextProps.archInfo.columns,
                nextProps.list.evalContext
            );
            this.keyOptionalFields = `${this.optionalDefaultsBaseKey},${nextConditionKey}`;
            this.optionalDefaultsEvalContext = nextProps.list.evalContext;
            this.getOptionalActiveFields();
            this.optionalDefaultsEvalContext = null;
            this.state.columns = this.getActiveColumns(nextProps.list);
        });
    },

    createKeyOptionalFields() {
        const baseKey = this._super(...arguments);
        if (!hasOptionalDefaults(this.allColumns)) {
            return baseKey;
        }
        const conditionKey = optionalDefaultsConditionKey(
            this.allColumns,
            this.props.list.evalContext
        );
        if (conditionKey === null) {
            return baseKey;
        }
        this.optionalDefaultsBaseKey = baseKey;
        this.optionalDefaultsConditionKey = conditionKey;
        return `${baseKey},${conditionKey}`;
    },

    getOptionalActiveFields() {
        const evalContext = this.optionalDefaultsEvalContext || this.props.list.evalContext;
        if (hasOptionalDefaults(this.allColumns)) {
            const conditionKey = optionalDefaultsConditionKey(this.allColumns, evalContext);
            if (conditionKey !== null) {
                this.optionalDefaultsBaseKey = this.optionalDefaultsBaseKey || this.keyOptionalFields;
                this.optionalDefaultsConditionKey = conditionKey;
                this.allColumns = applyOptionalDefaults(this.allColumns, evalContext);
            }
        }
        return this._super(...arguments);
    },
});
