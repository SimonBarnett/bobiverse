# FR-008 Login page shows the existing butler graphic

GitHub: #6816. Stays open. Split from closed bundle #6798.

## Goal

The Jeeves login page shows the existing butler graphic. Do not draw a new character.

## Deliverables

- The rendered login HTML includes jeeves/assets/jeeves-butler.ico.
- No new character image is added for this slice.

## Testable

- Rendered login HTML contains jeeves-butler.ico.
- jeeves/assets/ gains no new image file in this change.

## Out of scope

The /jeeves route (#6815), the Bob home-page link (#6818), the sign-in POST (#6819), the settings cookie gate (#6820), the appliance doc (#6821), and token graphs (#6784).
