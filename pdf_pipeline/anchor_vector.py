import os
import numpy as np
from langchain_openai import OpenAIEmbeddings
from dotenv import load_dotenv

load_dotenv()

file_name = 'anchor_vec.npy'

def save_embedding(text: str, filename: str):
    # Initialize the model
    embeddings_model = OpenAIEmbeddings(api_key=os.getenv("OPENAI_API_KEY"))
    
    print(f"Generating embedding for: '{text[:30]}...'")
    vector = embeddings_model.embed_query(text)
    
    vector_array = np.array(vector)
    
    np.save(filename, vector_array)
    print(f"Saved to {filename}")

def load_embedding(filename=file_name):
    vector = np.load(filename)
    return vector

if __name__ == "__main__":
    my_text = ('''
    Context: This text represents the structural and administrative components of a formal document rather than its topical or narrative content.

    Core Characteristics to Include:

    Navigation and Hierarchy: Phrases found in a Table of Contents or Index, including section titles, chapter numbers, and trailing dots or page numbers (e.g., "1.1 Introduction .... 5").

    Document Metadata: Header and footer information, such as document IDs, version numbers, dates, file paths, and repetitive page numbering (e.g., "Page 12 of 150").

    Reference and Citation Structure: Scientific or academic citation formatting, such as parenthetical author-dates, bracketed numbers, and long lists of bibliographical references with publishers and DOIs.

    Formal Boilerplate: Legal disclaimers, copyright notices, "This page intentionally left blank," and organizational branding or mission statements.

    Non-Narrative Fragments: Isolated lines consisting of figure labels, table titles, or fragments of data rows that lack grammatical sentence structure.
    ''')
    file_path = "content_check_vec.npy"
    
    # Save it
    save_embedding(my_text, file_path)
    
    # Load it back to verify
    loaded_vector = load_embedding()
    
    print(f"Successfully loaded vector with dimension: {len(loaded_vector)}")
    print(f"First 5 values: {loaded_vector[:5]}")