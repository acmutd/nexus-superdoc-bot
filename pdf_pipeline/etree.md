# EmbedTree — Semantic Document Tree Module

This module provides a hierarchical, embedding-aware tree structure for parsing, analyzing, and reconciling Markdown/PDF content against an existing document structure stored in a vector database (e.g., Pinecone).

---

## Overview

The core of this module is `EmbedTreeNode` — a wrapper around `markdown-it-py`'s `SyntaxTreeNode` that augments each node with:

- **OpenAI vector embeddings** for semantic comparison
- **Hierarchical parent/child relationships** based on heading level
- **Reconciliation logic** for matching new content to existing document headings
- **Pruning and insertion utilities** for structural manipulation

---

## Constants

| Constant | Default | Description |
|---|---|---|
| `MIN_BLOCK_LEN` | `2` | Minimum word count for a node to be considered meaningful |
| `SIMILARITY_THRESHOLD` | `0.97` | Cosine similarity cutoff for matching a node to an existing DB heading |

---

## Class: `EmbedTreeNode`

### Constructor

```python
EmbedTreeNode(
    node: SyntaxTreeNode,
    emb_model: OpenAIEmbeddings,
    parent: EmbedTreeNode | None,
    is_custom: bool = False
)
```

Wraps a raw `SyntaxTreeNode` with embedding and structural metadata.

**Instance Attributes**

| Attribute | Type | Description |
|---|---|---|
| `node` | `SyntaxTreeNode` | The underlying markdown-it node |
| `type` | `str` | Node type (e.g., `heading`, `paragraph`, `root`) |
| `emb_model` | `OpenAIEmbeddings` | The embedding model used for vector generation |
| `emb` | `np.ndarray \| None` | This node's own embedding vector |
| `mean_emb` | `np.ndarray \| None` | Mean of this node + all descendant embeddings |
| `parent` | `EmbedTreeNode \| None` | Parent node in the tree |
| `children` | `list[EmbedTreeNode]` | Child nodes |
| `content` | `str` | Text content of the node |
| `block_len` | `int` | Word count of the node's content |
| `has_embedding` | `bool` | Whether an embedding has been computed for this node |
| `is_pruned` | `bool` | Marked for removal during reconciliation |
| `is_custom_node` | `bool` | Whether this node was synthetically generated (not from the original PDF) |
| `has_custom_node` | `bool` | Whether any descendant is a custom node |

---

### Class Methods

#### `_init_tree(root_node, emb_model) -> EmbedTreeNode`
Builds a full `EmbedTreeNode` tree from a raw `SyntaxTreeNode` root. Respects heading hierarchy using a level stack — `h1` > `h2` > `h3`, etc. Heading text is extracted from leaf nodes to avoid markdown symbol contamination.

#### `_extract_text_recursive(node) -> str`
Gathers clean text from leaf nodes only to prevent duplication from parent content attributes containing markup.

#### `_build_internal_children(node, wrapper, emb_model)`
Recursively wraps non-heading children (paragraphs, list items, inline elements) and attaches them to their parent wrapper.

#### `_calc_block_len(node)`
Recursively accumulates word counts from children up to the root so each node reflects the total word count of its entire subtree.

#### `_calc_mean_embedding(node)`
Recursively computes a mean embedding for each node by averaging all non-null embeddings across itself and its descendants. Used for semantic matching at the subtree level.

#### `_embed_tree_(node)`
Finds all heading nodes in the tree, batch-embeds their text using the `OpenAIEmbeddings` model, and assigns the resulting vectors.

#### `_insert_custom_before(node, custom_node)`
Inserts `custom_node` as a new parent directly above `node` in the tree. Includes circular reference protection.

#### `_insert_batch_before(batch_node)`
Takes a custom batch node (whose children are a group of sibling nodes) and re-parents all children under `batch_node`, inserting it at the correct position in the original parent's child list.

#### `remove_branch(node)`
Detaches a node from its parent, severing the parent reference.

---

### Instance Methods

#### `mark_structural_mismatch(target_heading, node_heading_pairs)`
Marks child nodes as `is_pruned` if they carry a heading label that doesn't match the expected `target_heading`. Does not recurse into pruned branches.

#### `mark_semantic_mismatch(anchor_vector, threshold=0.8)`
Marks child nodes as `is_pruned` if their `mean_emb` cosine similarity to `anchor_vector` falls below `threshold`. Used to remove content that drifts semantically from the section it was assigned to.

#### `execute_pruning() -> Generator[EmbedTreeNode]`
Physically removes all nodes marked `is_pruned` from the tree and yields them. Recurses into non-pruned children.

#### `reconcile_structure(headings: list[dict]) -> tuple[list, list]`
The main reconciliation pipeline. Steps:

1. Converts raw `headings` dicts into `DB_Heading` objects
2. Finds "straggler" content (nodes with no parent heading) via `find_straggler_branches`
3. Samples text from each straggler batch and generates synthetic headings via LLM
4. Wraps each batch in a new custom `EmbedTreeNode` and inserts it into the tree
5. Embeds the new synthetic headings and computes mean embeddings for the full tree
6. Matches tree nodes to DB headings using cosine similarity
7. Marks and executes structural/semantic pruning
8. Returns `(new_custom_nodes, all_custom_nodes)` — nodes needing DB insertion vs. all custom nodes

**Returns:**
- `new_cust_nodes`: Custom nodes not matched to any existing DB heading — need to be written to the DB and doc
- `all_cust_nodes`: All custom nodes, including matched ones for rendering

#### `apply(func) -> Generator`
Performs a depth-first traversal of the tree, yielding the result of `func(node)` for every non-root node. Useful for filtering, mapping, or collecting nodes.

```python
# Example: collect all heading nodes
headings = [n for n in root.apply(lambda n: n) if n.type == 'heading']
```

#### `display_custom_headings(level=0)`
Prints a hierarchical view of all custom (synthetically generated) nodes in the tree. Useful for debugging reconciliation output.

---

### Static Methods

#### `get_full_text(node) -> str`
Recursively gathers and joins all text content from a node and its descendants, separated by newlines.

#### `find_straggler_branches(node) -> Generator[list[EmbedTreeNode]]`
Yields groups of sibling nodes that are "orphaned" — i.e., not beneath any heading anchor and not custom nodes themselves. Used to identify content that needs a generated heading.

A node is treated as a **boundary** (anchor) if it:
- Has `is_custom_node = True`
- Has `has_embedding = True`
- Is a `heading` type

#### `rows_to_headings(rows: list[dict]) -> list[DB_Heading]`
Converts raw database dictionaries into `DB_Heading` Pydantic objects. Malformed rows are skipped with a warning.

---

### Nested Model: `DB_Heading`

```python
class DB_Heading(BaseModel):
    id: str
    heading: Optional[str]
    position: Optional[int]
    embedding: List[float]
```

Represents a heading record as stored in the vector database.

---

## Module-Level Functions

### `get_sampled_text(nodes: list[EmbedTreeNode]) -> str`

Joins the full text of a list of nodes and returns a three-point sample:
- First 30 characters
- 30 characters from the middle
- Last 30 characters

Used to generate representative snippets for LLM heading generation without sending full document text.

---

### `generate_headings_from_sentences(sentences: list[str]) -> list[str]`

Generates concise, title-case document section headings for a list of text samples using `gpt-4o-mini`. Headings are 4–7 words, punctuation-free, and batch-invoked in parallel.

Falls back to `"Basic"` for any failed individual prompt.

**Parameters:**
- `sentences`: A list of text snippets (typically from `get_sampled_text`)

**Returns:** A list of heading strings, one per input sentence, in the same order.

---

### `find_closest_cosine_sim(query_vec, list_vecs) -> tuple[int, float]`

Finds the most similar vector in `list_vecs` to `query_vec` using normalized cosine similarity.

**Parameters:**
- `query_vec`: A 1D numpy array (the query embedding)
- `list_vecs`: A 2D numpy array of candidate embeddings

**Returns:** `(index_of_closest, similarity_score)`

---

## Dependencies

| Package | Usage |
|---|---|
| `pymupdf` / `pymupdf4llm` | PDF parsing and Markdown conversion |
| `markdown-it-py` | Markdown parsing into `SyntaxTreeNode` trees |
| `langchain-openai` | `OpenAIEmbeddings` and `ChatOpenAI` |
| `numpy` | Vector math and cosine similarity |
| `pydantic` | `DB_Heading` model validation |
| `python-dotenv` | Environment variable loading |

---

## Example Usage

```python
from io import BytesIO
from langchain_openai import OpenAIEmbeddings
from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode

# 1. Parse Markdown into a SyntaxTreeNode
md = MarkdownIt()
tokens = md.parse("# Introduction\n\nSome paragraph text here.")
root_syntax = SyntaxTreeNode(tokens)

# 2. Build the EmbedTree
emb_model = OpenAIEmbeddings()
root = EmbedTreeNode._init_tree(root_syntax, emb_model)

# 3. Embed all headings
EmbedTreeNode._embed_tree_(root)

# 4. Calculate subtree mean embeddings
EmbedTreeNode._calc_mean_embedding(root)

# 5. Reconcile against existing DB headings
db_headings = [{"id": "abc", "heading": "Introduction", "position": 0, "embedding": [...]}]
new_nodes, all_nodes = root.reconcile_structure(db_headings)
```