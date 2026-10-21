# Sample conversations

These examples illustrate interaction only. Any figures in the API request are
synthetic test inputs and are not Azure prices, customer data, or recommendations.

## Planning estimate

**User:** How much could we save with Azure Savings Plans?

**Assistant:** I can run a planning estimate using your eligible hourly PAYG
cost history. What currency should I use, what term do you want to model, and
what discount assumption has your team approved? You can paste hourly values or
upload a CSV with timestamp and eligible PAYG cost columns.

**User:** Use this synthetic test input: USD, P1Y, a 15% modeled discount, no
usage change, and the attached hourly CSV.

**Assistant:** I’ll pass those explicit assumptions to the planning API. The
result will be an estimate, not an Azure recommendation or guaranteed savings.

## Connected analysis

**User:** Analyze my Azure environment.

**Assistant:** Please sign in and provide the subscription or billing scope to
analyze. Also choose a 1-year or 3-year term, a 7-, 30-, or 60-day lookback,
and Single or Shared recommendations. I’ll request only the scope you specify.

**User:** Use the connected recommendation for the scope I selected.

**Assistant:** I’ll retrieve the recommendation from Azure Cost Management and
summarize the returned result. If Azure returns no recommendation or access is
denied, I’ll report that rather than estimate a connected result.

## Compare terms

**User:** Compare one-year and three-year options.

**Assistant:** I can compare no commitment, P1Y, and P3Y from the same hourly
cost history. Please provide the currency, expected usage change, and a
user-approved modeled discount for each term. I won’t assume a larger discount
for the longer term.

**User:** Why is the balanced scenario lower than maximum savings?

**Assistant:** The API models the balanced scenario from the median historical
hourly cost and maximum savings from a higher historical percentile. The larger
commitment can cover more usage, but can also leave more unused commitment if
usage falls. These transparent scenarios do not reproduce Microsoft's
recommendation algorithm.
