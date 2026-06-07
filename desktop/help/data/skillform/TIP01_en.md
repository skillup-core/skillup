# How to Create a Board

A board is made of **two JSON files**: a **list form** and a **detail form**.

- **List form**: A form with a single `board` type field. Displays records in a table format.
- **Detail form**: A regular form for reading and editing a single record. Opens when you click a row in the list.

The two files are connected by the `detailFormPath` property in the list form.

## Step 1: Create the Detail Form

The detail form shows the content of a single record.

**Field Composition (Feedback Example):**

| Field ID | Type | Description |
|---|---|---|
| `title` | `text` | Title input field |
| `body` | `textarea` | Content area (supports markdown) |
| `f3` | `dropdown` | Status (New / Review / Resolved ...) |
| `f12` | `info` | Display system field `@row_id` |
| `f13` | `info` | Display system field `@author` |
| `f14` | `info` | Display system field `@created_at` |
| `f16` | `comment` | Comment section |

**Buttons use the `boardCommand` property to specify their action:**

| `boardCommand` | Action |
|---|---|
| `POST` | Create a new record |
| `MODIFY` | Edit the current record |
| `DELETE` | Delete the current record |
| `LIST` | Return to the list |

**System fields** (`@row_id`, `@author`, `@created_at`, etc.) are automatically populated when you specify them in the `infoField` property of an `info` type field.

## Step 2: Create the List Form

The list form needs only a single `board` type field.

**Core Properties:**

```json
{
  "id": "board1",
  "type": "board",
  "detailFormPath": "desktop/board/suggest/form/detail.json",
  "listColumns": [
    { "id": "@row_id",     "width": "8"    },
    { "id": "@author",     "width": "15"   },
    { "id": "@created_at", "width": "15"   },
    { "id": "f3",          "width": "8"    },
    { "id": "title",       "width": "rest" }
  ]
}
```

- `detailFormPath`: Path to the detail form JSON (relative to project root)
- `listColumns`: Columns to display in the list and their widths. Use **field IDs from the detail form** or system field IDs.

## Column Width Specification

| Value | Meaning |
|---|---|
| Number (e.g., `"15"`) | Percentage of total width (15%) |
| `"rest"` | Fill remaining space (use on only one column) |

## Permissions

Control read/write/comment/modify permissions with the `permission` property.

```json
"permission": {
  "groupName": "FEEDBACK",
  "read":    { "nonMember": true },
  "write":   { "member": true    },
  "comment": { "member": true    },
  "modify":  { "admin": true     }
}
```

| Permission | Description |
|---|---|
| `read` | View list and detail content |
| `write` | Create new records, edit/delete own records |
| `comment` | Write comments |
| `modify` | Edit/delete others' records, change permissions |

Set `nonMember: true` to allow viewing without login.
