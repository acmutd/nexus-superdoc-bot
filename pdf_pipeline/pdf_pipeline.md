# Document Tree Reconciliation Engine

This module implements the `EmbedTreeNode` architecture, a hierarchical system designed to reconcile raw PDF structural trees (parsed via `markdown-it`) with a pre-defined database of headings. It uses a combination of vector similarity, LLM-based heading refinement, and structural pruning.

---

## 1. Core Architecture

### `EmbedTreeNode`
The primary class that wraps `SyntaxTreeNode`. It maintains parent-child pointers and stores metadata required for semantic alignment.

* **Attributes**:
    * `content`: The textual content of the node (either original markdown or LLM-generated).
    * **Vector State**: `emb` (NumPy array) and `has_embedding` (boolean).
    * **Audit Flags**: `is_custom_node` (synthetic nodes), `is_pruned` (nodes removed during reconciliation), and `needs_gen_heading`.
    * **Structure**: `parent` (reference) and `children` (list of siblings).

### `DB_Heading` (Pydantic Model)
Represents the "Source of Truth" against which the PDF is reconciled.
* `heading`: The canonical string name.
* `embedding`: The 1536-dimensional float list used for comparison.

---

## 2. The Reconciliation Pipeline (`reconcile_structure`)

The algorithm follows a specific sequence to ensure high-accuracy alignment:



1.  **Discovery**: Traverses the tree to find "Stragglers"—content blocks that exist without a valid heading parent.
2.  **Synthesis**: Extracts a text sample (start, middle, and end) from straggler batches to provide context.
3.  **LLM Refinement**: Sends samples to `gpt-4o-mini` to generate professional, title-case headings.
4.  **Structural Grafting**: Uses `_insert_batch_before` to surgically inject the new heading nodes as parents of the stragglers.
5.  **Vector Alignment**: Embeds the new headings and uses `match_headings` to find the closest database match via cosine similarity.
6.  **Hierarchical Enforcement**: Runs `remove_different_heading_child_branches` to prune branches that claim a database identity contradicting their parent's category.

---

## 3. Method Reference

### Primary Operations
| Method | Description |
| :--- | :--- |
| `reconcile_structure` | The main execution loop. Orchestrates generation, insertion, and pruning. |
| `match_headings` | Compares `node.emb` against `heading_vecs` using a `SIMILARITY_THRESHOLD` (default 0.97). |
| `remove_different_heading_child_branches` | Recursively "locks" a branch to a DB heading and prunes children with conflicting matches. |

### Structural Helpers
* **`_insert_batch_before(batch_node)`**: Handles the "Structural Handshake." It detaches siblings from their original parent and re-attaches them under the new custom node, maintaining the original document index.

* **`find_straggle_branches(node)`**: A generator that yields lists of nodes that are not protected by a "custom" or "heading" path.
* **`get_full_text(node)`**: Recursively gathers all text from a node's entire subtree.

---

## 4. Key Configurations

* **`MIN_BLOCK_LEN` (10)**: Nodes with fewer words than this are ignored for heading generation to avoid creating headings for noise/page numbers.
* **`SIMILARITY_THRESHOLD` (0.97)**: A strict threshold ensuring only high-confidence matches are locked into the database schema.
* **Sampling**: Uses a 3-point extraction (30 chars each from start/mid/end) to minimize token usage while maximizing context.

---

## 5. Usage Example

```python
# Initialize the tree
root = EmbedTreeNode._init_tree(syntax_tree, emb_model)

# Reconcile against DB headings
db_headings = [DB_Heading(**data) for data in db_results]
new_nodes, all_attempts = root.reconcile_structure(db_headings)

# Audit findings
print(f"Total Custom Nodes Created: {len(all_attempts)}")
print(f"Nodes without DB matches: {len(new_nodes)}")

# Print final structure
print(root)