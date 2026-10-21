# Customer sharing checklist

Complete this checklist for the target customer's tenant and repository before
sharing or deploying:

- [ ] Confirm all sample identifiers and amounts are synthetic. Do not include
      customer usage history or billing-scope identifiers in source control.
- [ ] Review the git history and CI artifacts for secrets, tokens, tenant or
      subscription identifiers, customer names, and exported cost data.
- [ ] Confirm CI passes, including unit tests, compilation, OpenAPI parsing, and
      Bicep compilation.
- [ ] Review the what-if assumptions and calculation model with the customer's
      FinOps owner. Ensure the modeled discount is user-approved and not
      presented as a price quote.
- [ ] Keep connected Cost Management recommendations distinct from what-if
      and comparison estimates.
- [ ] For the Windows app, verify Azure CLI user sign-in, tenant switching,
      subscription membership filtering, and Advisor/Cost Management read RBAC.
      Connected desktop analysis must work without a CSV. Explain that CLI
      credentials are shared with the user's CLI and Disconnect only clears app
      context. The desktop does not require a separately deployed Function.
- [ ] Verify read access for VM, VM scale set and App Service plan inventory.
      Distinguish current configured SKU/license evidence from historical usage,
      benefit eligibility, entitlement and actual discount/coverage. Plan-level
      inventory is context only; Advisor enrichment requires an exact resource ID.
- [ ] Test the released Windows installer and checksum, including application
      launch/uninstall under an isolated test user. Disclose that it is unsigned.
- [ ] Configure the customer's Entra app registration, OAuth scope, delegated
      Azure Resource Manager permission, consent, and redirect URI through the
      approved identity process.
- [ ] Deploy through the Flex Consumption Bicep template using the intended
      tenant, subscription, region, and resource group. Confirm all role
      assignments before validation.
- [ ] Verify the Key Vault uses Azure RBAC, the Function's managed identity is
      permitted to resolve only the intended secret, and the secret is not
      present in application source or deployment logs.
- [ ] Grant Cost Management read permission only to the intended users at the
      approved billing scope. This repository does not create those grants.
- [ ] Replace the host, OAuth tenant/client placeholders, and CORS origins in
      the OpenAPI tool configuration. Do not use wildcard CORS or Function-key
      authentication for production.
- [ ] Confirm App Service Authentication rejects unauthenticated API requests,
      except the minimal `/api/health` endpoint.
- [ ] Test permission-denied, empty-recommendation, malformed CSV, and
      unavailable Azure API behavior without using production customer data.
- [ ] Explain that no automated Savings Plan purchasing or changes are
      performed and that estimates are not guaranteed savings.
