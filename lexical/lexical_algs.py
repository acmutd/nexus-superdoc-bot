
import re
import gc 


def get_hashed_shingles(text, n=2): # Lowered to n=2
    # Define a small list of 'stop words' to ignore
    stop_words = {'the', 'a', 'an', 'of', 'and', 'or', 'in', 'to', 'is', 'it', 'such', 'as'}
    
    # 1. Clean and tokenize
    tokens = re.sub(r'[^\w\s]', '', text.lower()).split()
    
    # 2. Filter out stop words
    filtered_tokens = [t for t in tokens if t not in stop_words]
    
    # 3. Create Hashed Bigrams
    return {hash(tuple(filtered_tokens[i : i + n])) for i in range(len(filtered_tokens) - n + 1)}

def calculate_jaccard(set1, set2):
    if not set1 or not set2: return 0.0
    return len(set1 & set2) / len(set1 | set2)

def extract_text_similarity_jaccard(text1,text2): 
    set1 = get_hashed_shingles(text1)
    set2 = get_hashed_shingles(text2)
    return calculate_jaccard(set1,set2)



if __name__ == "__main__": 
    paragraphs = [
    "The implementation of renewable energy solutions, such as solar and wind power, has become a critical priority for urban planners seeking to reduce carbon footprints. By integrating photovoltaic panels into building designs and establishing large-scale offshore wind farms, cities can significantly decrease their reliance on fossil fuels. This transition not only addresses the immediate concerns of climate change but also fosters economic growth through the creation of new green-technology jobs and infrastructure development projects that revitalize local economies.",
    
    "To reduce carbon footprints, urban planners are making the implementation of renewable energy solutions like wind and solar power a critical priority. Cities can notably decrease their fossil fuel reliance by establishing large-scale offshore wind farms and integrating photovoltaic panels into the designs of buildings. Not only does this transition address climate change concerns immediately, but it also promotes economic growth by creating new green-tech jobs and infrastructure projects that help revitalize local economies.",
    
    "Adopting sustainable power alternatives, including sun-based and breeze-driven systems, has turned into a vital goal for metropolitan architects aiming to lower environmental impacts. By incorporating light-harvesting boards into architectural blueprints and setting up massive sea-based turbine arrays, municipalities can greatly cut down on their use of coal and gas. This shift doesn't just tackle the pressing issues of global warming; it also encourages financial expansion by generating employment in eco-friendly industries and building ventures that breathe life into community markets.",
    
    "The history of Renaissance art is characterized by a profound shift toward realism and the use of linear perspective to create the illusion of depth. Masters like Leonardo da Vinci and Michelangelo revolutionized the way the human form was depicted, moving away from the flat, symbolic styles of the Medieval period. Their mastery of chiaroscuro—the contrast between light and dark—allowed for a level of emotional expression and anatomical accuracy that had never been seen before in Western European painting."
    ]   

    # Compare the Baseline (sentences[0]) against the others
    base_shingles = get_hashed_shingles(paragraphs[0])

    for i, s in enumerate(paragraphs):
        comp_shingles = get_hashed_shingles(s)
        score = calculate_jaccard(base_shingles, comp_shingles)
        print(f"Comparing Sentence 0 to Sentence {i}:")
        print(f"Score: {score:.2f}\n")