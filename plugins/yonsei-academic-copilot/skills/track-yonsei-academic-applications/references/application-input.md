# Application radar input

Use an object with `now` and `applications`. Each application row contains
`name`, `category`, `opens_at`, `closes_at`, `status`, `eligible`,
`missing_items`, and `source`. Use ISO 8601 times with an offset when possible.

Unknown eligibility is `null`, not `false`. A visible menu is not proof of
eligibility. The radar is read-only; submission happens only in the official
browser after an action-time confirmation.
