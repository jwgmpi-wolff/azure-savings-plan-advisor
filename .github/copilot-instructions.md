# GitHub Copilot repository instructions

Build and maintain this repository as a customer-shareable Azure Savings Plan Advisor accelerator.

## Non-negotiable rules
- Return complete replacement files, never partial patches in explanations.
- Do not invent Azure prices, discounts, savings, recommendations, usage, or customer data.
- Connected recommendations must come from Azure Cost Management APIs.
- What-if calculations must use explicit user-supplied assumptions and be labeled planning estimates.
- Keep the Copilot/agent experience appropriate for nontechnical users.
- Never add secrets, tenant IDs, subscription IDs, customer names, billing identifiers, tokens, or production endpoints to source control.
- Keep sample identifiers obviously synthetic.
- Keep calculation logic deterministic and unit-tested.
- Treat purchase actions as out of scope. This tool is decision support only.
- Before finalizing changes, run tests and security checks available in the repository.

## Target architecture
Copilot Studio -> REST/OpenAPI tool -> Python Azure Function -> Azure Cost Management Benefit Recommendations API.

## Quality bar
- Clear README suitable for a customer technical team.
- Reproducible local setup.
- Infrastructure as code for Azure deployment.
- Entra-based production authentication guidance.
- CI validation on pull requests.
- Customer-safe examples only.
