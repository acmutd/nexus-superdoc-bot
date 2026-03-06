# `GdocTreeNode` — Google Docs Request Generator

This module converts an `EmbedTreeNode` semantic tree into structured Google Docs API requests. It handles text insertion, paragraph formatting, heading styles, list rendering, and table construction.

---

## Overview

`GdocTreeNode` wraps an `EmbedTreeNode` and provides the rendering layer responsible for translating a parsed document tree into batched Google Docs API `insertText` and formatting requests. It mirrors the tree structure of its source `EmbedTreeNode`, but its sole purpose is generating the request payloads needed to physically write content into a Google Doc.

---

## Helper Function

### `text_utf16_len(text: str) -> int`
Returns the length of a string in UTF-16 code units — required for all index calculations in the Google Docs API, which uses UTF-16 encoding internally.

```python
text_utf16_len("Hello")
text_utf16_len("freaky ahh cuh")  
```

> **Important:** All index arithmetic in this module uses UTF-16 length, not Python's default `len()`.

---

## Class: `GdocTreeNode`

### Constructor

```python
GdocTreeNode(enode: EmbedTreeNode)
```

Wraps a single `EmbedTreeNode` with Google Docs rendering metadata.

**Instance Attributes**

| Attribute | Type | Description |
|---|---|---|
| `enode` | `EmbedTreeNode` | The source semantic tree node |
| `node` | `SyntaxTreeNode` | The underlying markdown-it node |
| `type` | `str` | Node type (e.g., `heading`, `paragraph`, `root`) |
| `content` | `str` | Text content, sourced from the `EmbedTreeNode` |
| `children` | `list[GdocTreeNode]` | Wrapped child nodes |
| `is_custom_node` | `bool` | Whether this node was synthetically generated |

---

### Class Methods

#### `_init_tree(etree: EmbedTreeNode) -> GdocTreeNode`
Recursively wraps an entire `EmbedTreeNode` tree into a `GdocTreeNode` tree, preserving the same parent/child hierarchy.

```python
gdoc_root = GdocTreeNode._init_tree(embed_root)
```

---

### Instance Methods

#### `generate_formatted_requests(start_index, level=0, context=None) -> tuple[list[dict], list[dict], int]`

The primary rendering method. Recursively traverses the tree and generates two ordered lists of Google Docs API request objects, plus a total character offset.

**Parameters:**
| Parameter | Type | Description |
|---|---|---|
| `start_index` | `int` | The current UTF-16 cursor position in the Google Doc |
| `level` | `int` | Depth in the tree, used for heading level and indentation math |
| `context` | `dict \| None` | Propagated context (e.g., `list_mode: "BULLET"` or `"ORDERED"`) |

**Returns:** `(text_requests, format_requests, total_offset)`
- `text_requests`: Ordered `insertText` API calls
- `format_requests`: Ordered style/paragraph update calls
- `total_offset`: Total UTF-16 character length inserted, used to advance the cursor for subsequent nodes

**Rendering rules:**
- Custom nodes (synthetically generated headings) are **skipped** for text insertion — they act as structural containers only
- `paragraph` nodes are treated as **leaf renderers** — they do not recurse into their children; text is extracted directly
- `bullet_list` / `ordered_list` nodes pass list context down to child paragraphs but insert no text themselves
- `list_item` nodes delegate rendering to their paragraph children via context

---

#### `_dispatch_node_type(index, level, context) -> tuple[list[dict], list[dict], int]`

Routes a node to its appropriate formatting method based on `node.type` and `is_custom_node`. Returns empty requests for node types that are containers or not yet rendered (lists, list items, custom headings).

| Node Type | Behavior |
|---|---|
| `is_custom_node = True` | Returns empty — structural only |
| `heading` | Calls `_format_heading` |
| `paragraph` | Calls `_format_paragraph_as_leaf` |
| `bullet_list` / `ordered_list` | Returns empty, sets list context |
| `list_item` | Returns empty, handled by paragraph child |
| All others | Returns empty |

---

#### `_format_heading(index, level) -> tuple[list[dict], list[dict], int]`

Generates an `insertText` request and a `updateParagraphStyle` request to render a heading at the appropriate level (`HEADING_1` through `HEADING_6`).

Heading level is derived from tree depth, capped at 6. Content is sourced from `enode.content`.

---

#### `_format_paragraph_as_leaf(index, level, context) -> tuple[list[dict], list[dict], int]`

Renders a paragraph node by:
1. Extracting clean text via `_extract_clean_text`
2. Appending `\n\n` as a paragraph terminator
3. Computing UTF-16 length for accurate index tracking
4. Applying indentation using Google Docs' `indentFirstLine` and `indentStart` paragraph style fields (36pt per depth level)
5. Optionally wrapping the paragraph in a bullet using `createParagraphBullets` if a `list_mode` is present in context

**Indentation logic:**

| Mode | `indentFirstLine` | `indentStart` |
|---|---|---|
| Standard text | `(level + 1) * 36pt` | `(level + 1) * 36pt` |
| Bullet/List | `level * 36pt` | `(level + 1) * 36pt` |

The offset between `indentFirstLine` and `indentStart` creates the hanging indent for bullet points.

---

#### `_extract_clean_text(node) -> str`

Recursively collects text from `text`-type leaf nodes only, avoiding duplication from intermediate `inline` nodes that may aggregate their children's content in their own `content` attribute.

---

#### `_build_native_table_requests(raw_content, start_index, level) -> tuple[list[dict], list[dict], int]`

Parses a Markdown table string and generates Google Docs API requests to:
1. Insert an empty table with the correct row/column dimensions
2. Fill each cell with text using sequential index arithmetic
3. Bold the first row (header row)

**Index arithmetic:** Each cell boundary occupies 2 index units in the Google Docs model. The cursor advances by `text_utf16_len(cell_text) + 2` per cell.

**Returns:** `(text_requests, format_requests, total_offset)`

---

#### `__str__() -> str`

Returns a human-readable tree representation for debugging. Each node is printed with:
- Depth indicator (`[D:N]`)
- Node type and HTML tag
- `[CUSTOM]` flag if applicable
- A 50-character content snippet

---

## Context Propagation

List context is passed downward through the tree during `generate_formatted_requests`. When a `bullet_list` or `ordered_list` node is encountered, it sets `list_mode` in the context dict, which is then read by descendant `paragraph` nodes to apply bullet formatting.

```
bullet_list          ← sets context["list_mode"] = "BULLET"
  └─ list_item
       └─ paragraph  ← reads list_mode, applies createParagraphBullets
```

---

## Example Usage

```python
from pdf_pipeline.etree import EmbedTreeNode
from pdf_pipeline.gdoc_tree import GdocTreeNode

# 1. Build the EmbedTreeNode tree (from your PDF pipeline)
embed_root: EmbedTreeNode = ...

# 2. Wrap it in a GdocTreeNode tree
gdoc_root = GdocTreeNode._init_tree(embed_root)

# 3. Generate all API requests, starting at index 1 (Google Docs body start)
text_requests, format_requests, total_len = gdoc_root.generate_formatted_requests(start_index=1)

# 4. Execute requests against the Google Docs API
# Text must be inserted before formatting is applied
docs_service.documents().batchUpdate(
    documentId=DOCUMENT_ID,
    body={"requests": text_requests + format_requests}
).execute()
```

> **Note:** Always apply `text_requests` before `format_requests`. Formatting requests reference index ranges that only exist after text has been inserted.

---

## Dependencies

| Package | Usage |
|---|---|
| `markdown-it-py` | `SyntaxTreeNode` node types and tag metadata |
| `langchain-openai` | Inherited via `EmbedTreeNode` |
| `pdf_pipeline.etree` | `EmbedTreeNode` source tree |