# History and Diff Comparison

## Automatic History Snapshots

When you close an editing session (return to list), a snapshot is saved automatically if the content changed. Up to 10 snapshots are kept per document.

## History Panel

Click the **[History]** button in the editor header to open the history list.

| Button | Action |
|--------|--------|
| **View** | Show that snapshot in read-only mode |
| **Compare with current** | Diff that snapshot against the current content |
| **Compare with previous** | Diff two adjacent snapshots |
| **Apply** | Overwrite the current document with that snapshot |

## Diff Mode

A split-screen view places OLD on the left and NEW on the right.

- Markdown body: changed words are highlighted with a **colored border**
- TODO / Checklist: changed rows are highlighted with background color
- Click **[Exit diff]** to return to normal editing mode
