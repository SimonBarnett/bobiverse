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
