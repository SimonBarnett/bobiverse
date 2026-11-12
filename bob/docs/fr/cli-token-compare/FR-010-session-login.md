# FR-010 Login form uses the existing session login

GitHub: #6819. Stays open. Split from closed bundle #6798.

## Goal

The login form on /jeeves posts username, optional domain, and password to the existing session login. Passwords are not logged.

## Deliverables

- The form posts those three fields to the existing session login.
- A sign-in from this page reaches that login.
- Passwords are not logged.

## Testable

- The login POST accepts username, optional domain, and password.
- A test shows the password value is absent from the log line for that POST.

## Out of scope

The public GET route (#6815), the butler graphic (#6816), the Bob home-page link (#6818), the settings and status cookie gate (#6820), the appliance doc (#6821), and token graphs (#6784).

## Implementation (MRB #6838)

- Login HTML has one account field (name="account") plus optional Domain (name="domain") and password.
- The form JSON-posts username, domain, and password to POST /api/login (existing session login).
- Password values are absent from the access log line for that POST.
- FR #6749 one-account pin stays; the old no-name=domain HTML pin was updated on PR #6838 because FR-010 requires the optional domain field.
