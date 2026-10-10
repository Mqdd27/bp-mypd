# Mayapada eProc stress API in Postman

These endpoints perform real Odoo ORM transactions. Use only against a disposable/local/test database unless explicitly approved.

## Import and sign in

1. Import `Mayapada-eProc-Stress.postman_collection.json` into Postman.
2. Import `Mayapada-Local.postman_environment.json` and select **Mayapada-Local**.
3. Set `password` locally in the Postman environment. The imported value is empty. Never export or share an environment containing credentials.
4. Run **00 - Authentication / Login**. It uses Odoo's native `/web/session/authenticate` JSON-RPC route for `mayapada-local`; do not use the Mayapada `/api/auth` route for this local database.
5. Run **00 - Authentication / Health Check**. Postman's cookie jar sends the `session_id` set by Odoo. Do not copy the cookie into an environment variable or a request header.
6. Execute later requests **manually** in workflow order. Do not run the entire collection: several requests create or advance real documents.

## Workflow and variables

- **904 Create PR** uses IDs verified in `mayapada-local`. Each send creates a new PR. Its success test saves `data.id` to `{{pr_id}}`; it does not use the prior test PR ID 18. Confirm and Approve use the saved ID. The flow is **Create PR → Draft → Confirm → Approval workflow → Approve using the appropriate authenticated Odoo user**. One approval call may leave further approvals pending.
- **905 Create RFQ** saves `{{rfq_id}}`. **Create RFQ From PR** also saves the first returned RFQ ID. Its request body shows direct realization; its description contains a separate tender body. Set `{{request_line_id}}` from a verified eligible PR line; Create PR does not return line IDs.
- **906 Create Agreement** saves `{{agreement_id}}`. This endpoint covers rate agreements only; tender/tabulation creation is outside its scope.
- **907 Generate Suggestions** invokes existing orderpoint suggestion logic and may create draft logs. **908 Realize Suggestions to PR** can create a draft PR or return a confirmation action.
- **909 Create Receipt** saves `{{receipt_id}}`. Its main body is PO; its description contains separate WO and RT bodies. Receiving validation can cause stock, accounting, and interfacing side effects.

The login and health checks and **904 Create PR** have been runtime validated. **904 Confirm/Approve and every 905–909 transaction request have not**. Their blank ID, price, and date variables are placeholders: inspect the local database and fill compatible values before sending. Numeric placeholders in JSON bodies intentionally have no quotes and make the body incomplete until populated. Do not treat the task 904 IDs as validation for another workflow.

Use Postman's environment editor to review `pr_id`, `rfq_id`, `agreement_id`, and `receipt_id` after successful create requests. Login uses Postman's cookie jar, and no collection script stores a password, session ID, or cookie.
