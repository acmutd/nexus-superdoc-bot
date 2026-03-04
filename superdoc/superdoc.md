# `superdoc` — Hierarchical PDF-to-Google-Doc Merging

The `superdoc` class automates the hierarchical merging of PDF content into Google Docs while maintaining a semantic representation of the data in Pinecone. It uses OpenAI embeddings to understand document structure and "fits" new content into existing headings.

---

## Core Dependencies

| Library | Purpose |
|---|---|
| **PyMuPDF / PyMuPDF4LLM** | High-fidelity PDF-to-Markdown conversion |
| **LangChain / OpenAI** | Semantic embeddings and text analysis |
| **Pinecone** | Vector storage for document headers and semantic structure |
| **GoogleDocsEditor** | Custom interface for programmatically manipulating Google Docs via Named Ranges and structural updates |

---

## Initialization

```python
__init__(DOCUMENT_ID: str | None, COURSE_ID: str, index_name: str = 'sdtest1')
```

Initializes the connection to Google Docs and Pinecone.

| Parameter | Description |
|---|---|
| `DOCUMENT_ID` | If `None`, a new Google Doc is automatically created and named after the `COURSE_ID` |
| `COURSE_ID` | Used as a partitioning key in Pinecone and Google Docs metadata |
| `index_name` | The target Pinecone index for vector operations (default: `'sdtest1'`) |

---

## Main Pipeline: Hierarchical Merging

```python
merge_pdf_hierarchical(stream: BytesIO)
```

The primary method for processing new material. Follows a six-step pipeline:

| Step | Action | Description |
|---|---|---|
| 1 | **Conversion** | Uses `pdf_to_syntree` to turn a raw PDF stream into a Markdown-based Syntax Tree |
| 2 | **Semantic Building** | Builds an `EmbedTree`, calculating vector embeddings for every paragraph and heading |
| 3 | **Context Retrieval** | Queries Pinecone for existing headings already present in the Google Doc |
| 4 | **Reconciliation** | Matches new PDF sections to existing headings or identifies "orphaned" content needing new headings |
| 5 | **Vector Sync** | Appends newly generated structural nodes (headings) to Pinecone |
| 6 | **Doc Rendering** | Manipulates the Google Doc to insert text into the correct sections using `mutate_named_ranges` |

---

## Heading Management

> **Important:** These methods ensure the Google Doc and Vector DB remain in perfect sync. Never update one without the other.

### `create_heading(new_heading: str)`
Creates a new physical heading in the Google Doc and registers it in the Pinecone index for future semantic matching.

### `delete_heading(old_heading: str)`
Locates the heading in Google Docs by its Named Range, removes the text, and purges the corresponding vector record from Pinecone.

### `update_heading(old_heading: str, new_heading: str)`
Renames an existing heading. Updates the text and Named Range in the Google Doc and replaces the metadata/text in the Vector DB while preserving existing vector ID relationships.

---

## Utility & Metadata Methods

### `get_docids(course_id: str) -> dict`
Scans the user's Google Drive/Environment for all documents associated with a specific course.

**Returns:** A dictionary mapping `Document Name -> Document ID`.

### `create_document(name: str, course_id: str)`
A standalone helper to generate a new SuperDoc without triggering the merge pipeline.

---

## Internal Logic

### `pdf_to_syntree(stream: BytesIO) -> SyntaxTreeNode` *(static)*

Converts a raw PDF byte stream into a traversable syntax tree.

1. Opens a PDF from a byte stream
2. Converts the layout to Markdown
3. Parses the Markdown into a `SyntaxTreeNode` (via `markdown-it-py`) for hierarchical traversal


## Related Modules

The pipeline internally relies on two submodules documented separately:

| Module | Path | Description |
|---|---|---|
| **EmbedTreeNode** | [`pdf_pipeline/etree.md`](../pdf_pipeline/etree.md) | Semantic embedding tree — parses PDF content into a heading-aware node tree with OpenAI vector embeddings and reconciliation logic |
| **GdocTreeNode** | [`pdf_pipeline/gdoctree.md`](../pdf_pipeline/gdoctree.md) | Google Docs rendering layer — converts an `EmbedTreeNode` tree into batched `insertText` and formatting API requests |