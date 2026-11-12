# FR-007 GET /jeeves returns the login page

GitHub: #6815. Stays open. Split from closed bundle #6798.

## Goal

GET /jeeves on the existing bob.ntsa.uk front returns the Jeeves appliance login HTML. A public GET is not a 403.

## Deliverables

- GET /jeeves returns the login HTML.
- The non-RFC1918 reject does not turn this page into a 403.
- /bob/v1/* is unchanged.

## Testable

- A test maps GET /jeeves to login HTML that contains a password field.
- That response is not 403.
- An existing /bob/v1/* route still matches its current path.

## Out of scope

The butler graphic (#6816), the Bob home-page link (#6818), the sign-in POST (#6819), the settings cookie gate (#6820), the appliance doc (#6821), and token graphs (#6784).
