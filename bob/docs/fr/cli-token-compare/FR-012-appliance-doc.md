# FR-012 Appliance doc states bob.ntsa.uk/jeeves

GitHub: #6821. Stays open. Docs only. Split from closed bundle #6798.

#6758 completed in PR #6792 and wrote the old hostname. This slice replaces those sentences. Do not reopen #6757 or #6758.

## Goal

The appliance doc tells the operator to open https://bob.ntsa.uk/jeeves.

## Deliverables

- jeeves/docs/jeeves-settings-appliance.md states the URL https://bob.ntsa.uk/jeeves.
- It no longer tells the operator to browse jeeves.ntsa.uk.
- It no longer says not to publish the UI on bob.ntsa.uk.

## Testable

- The appliance doc contains https://bob.ntsa.uk/jeeves.
- The appliance doc does not tell the operator to browse jeeves.ntsa.uk.
- The appliance doc does not say not to publish the UI on bob.ntsa.uk.

## Out of scope

Route code (#6815), the butler graphic (#6816), the Bob home-page link (#6818), the sign-in POST (#6819), the cookie gate (#6820), and token graphs (#6784).

## Implementation (MRB #6842)

- Operator URL in jeeves/docs/jeeves-settings-appliance.md is https://bob.ntsa.uk/jeeves.
- Operators are told not to browse jeeves.ntsa.uk.
- The doc no longer forbids publishing the UI on bob.ntsa.uk (Cloudflare and irc.ntsa.uk remain refused).
- Does not reopen #6757 / #6758.
