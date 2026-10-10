odoo.define('mayapada.mention_filter', function (require) {
    "use strict";

    const mailThread = require('mail.thread');
    const core = require('web.core');
    const _t = core._t;

console.log('MASUK SINI COK');

    mailThread.include({
        _fetchMentionedUsers: function (domain) {
            // Custom domain to filter partners with is_user=True
            const customDomain = [['is_user', '=', true]];

            return this._rpc({
                model: 'res.partner',
                method: 'search_read',
                args: [customDomain, ['name', 'id']],
            }).then(function (partners) {
                // Update the mention suggestions with the filtered partners
                this._mentionSuggestions = partners.map(partner => ({
                    id: partner.id,
                    name: partner.name,
                }));
                this._updateMentionList();
            });
        },
    });
});
