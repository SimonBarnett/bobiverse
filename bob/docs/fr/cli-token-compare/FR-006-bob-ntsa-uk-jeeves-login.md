# FR-006 bob.ntsa.uk/jeeves login

GitHub: #6798. Closed as the bundle. Do not implement this issue.

Successors: #6815 route, #6816 butler graphic, #6818 home link, #6819 session login, #6820 session cookie, #6821 appliance doc.

#6757 landed https://jeeves.ntsa.uk/ in PR #6791 and is closed. Do not extend that hostname. Do not reopen #6757.

## Goal

https://bob.ntsa.uk/jeeves is the Jeeves appliance login page. The existing Bob home page links to it. The page shows the existing butler graphic.

## Deliverables

- GET /jeeves on the existing bob.ntsa.uk front returns the login HTML. /bob/v1/* is unchanged.
- The login page includes jeeves/assets/jeeves-butler.ico. Do not draw a new character.
- jeeves/www/irc-ntsa/index.html has a visible link to /jeeves.
- The login form still posts username, optional domain, and password to the existing session login. A sign-in from this page reaches that login. Passwords are not logged.
- A public GET of /jeeves returns the login HTML. The non-RFC1918 reject must not turn this page into a 403.
- Settings and status still require the existing session cookie.
- jeeves/docs/jeeves-settings-appliance.md states the URL https://bob.ntsa.uk/jeeves. It no longer tells the operator to browse jeeves.ntsa.uk. It no longer says not to publish the UI on bob.ntsa.uk.

## Testable

- Rendered login HTML contains jeeves-butler.ico and a password field.
- jeeves/www/irc-ntsa/index.html contains href="/jeeves".
- A test maps GET /jeeves to that login HTML and shows the response is not 403.
- The appliance doc contains https://bob.ntsa.uk/jeeves.
- The appliance doc does not tell the operator to browse jeeves.ntsa.uk.
- The appliance doc does not say not to publish the UI on bob.ntsa.uk.

## Out of scope

Token graphs (#6784), pool pages (#6759 and siblings), webhook route changes, a new DNS name, and a new butler drawing.
