# FR-011 Settings and status stay behind the session cookie

GitHub: #6820. Stays open. Split from closed bundle #6798.

## Goal

Settings and status still require the existing session cookie after /jeeves is public.

## Deliverables

- Unauthenticated settings and status requests do not return the settings or status body.
- The existing session cookie still opens those pages.

## Testable

- A test GET of settings without the session cookie is rejected.
- A test GET of status without the session cookie is rejected.
- The same GETs with a valid session cookie return the existing pages.

## Out of scope

The public login GET (#6815), the butler graphic (#6816), the Bob home-page link (#6818), the appliance doc (#6821), and token graphs (#6784).
