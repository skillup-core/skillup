# Document Links and Inline Mentions

## Document Links (Link Button)

Click **[<]** in the editor header to expand the **Link** button. In the link dialog:

- Click a recent document to link it immediately
- Type a document ID to search and link by ID
- Links are **bidirectional** — linking A→B also shows A in B's link list

## Inline Document Link (`[[`)

While editing markdown, type `[[` to open a document search popup.

```
[[cadence setup memo]]
```

- The selected document is inserted as `[[42|cadence setup memo]]`
- Renders as a badge in preview mode; click to navigate to that document
- Links to deleted documents are shown with strikethrough

## Inline Mentions (`@`)

Type `@` to search team members and insert a mention.

```
@[greenfish|John Kim]
```
