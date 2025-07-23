#########################
### ENVIRONMENT SETUP ###
#########################

# Import modules
import difflib
import json
import openai
import os
import pandas as pd
import requests
import warnings

# Set gloabl variables
global func_flag
global init_flag
func_flag = False
init_flag = True

# Set API key
openai.api_key = os.getenv("OPENAI_API_KEY")

########################
### HELPER FUNCTIONS ###
########################

# Function: Call OpenAI API
def call_api(history, functions=None):
    chat_co = openai.chat.completions.create(
        model="gpt-4-turbo",
        messages=history,
        functions=functions,
        temperature=0.2,
        top_p=0.4
    )
    return chat_co.choices[0].message

# Function: Update chat history
def update_history(history, role, content, name=None):
    message = {"role": role, "content": content}
    if name:
        message["name"] = name
    history.append(message)

# Function: Initialize chat
def initialize(history):
    global init_flag
    
    # Add system task info
    task = "You are a neuroscience research assistant. You answer scientific \
questions using multiple resources and should draw on prior conversation \
history to maintain coherence. When details are unspecified, infer them based \
on recent context (e.g., assume the same cell type if the user referenced it \
most recently). You have access to the following tools to support scientific \
inquiry: \n1. gene_expression Function: Returns gene expression and protein \
prevalence data for specific cell types and brain vasculature regions, based \
on single-nucleus RNA sequencing (snRNA-seq) from the Brain Resilience \
Laboratory at Stanford University. \n2. Biomedical Knowledge Graph: A curated \
knowledge graph based on SPOKE (from UCSF), containing molecular and disease \
biology relationships. \n3. Google Search API: Allows web search for \
up-to-date biomedical information. \n4. Pretrained Scientific Knowledge: You \
may also draw on your own scientific knowledge acquired during pre-training. \n\
WHEN TO CALL gene_expression: \n- If the user asks about gene expression or \
protein prevalence in a cell type and/or brain region, and does NOT specify a \
tissue type, ASSUME they mean brain vasculature and call the function. \n- If \
the user asks: `Is gene X among the top Y expressed genes in brain region Z?`, \
check all listed genes for each of the specified brain regions using the \
function. \n- If the user explicitly mentions vasculature (e.g., `in \
vasculature`, `vascular tissue`, `blood vessels`), call the function. \n\
Response Notes: \n- If the data returned only relates to a brain region, you \
MUST state in your response: `This answer reflects all cell types across the \
specified brain region. \n- If the data returned only relates to a cell type, \
you MUST state: `This answer reflects the specified cell type across all brain \
regions.` \n- If tissue type is unspecified but both cell type and brain \
region are given, add: `Since you specified a cell type and brain region but \
did not mention tissue type, I’ve assumed brain vasculature.` \n- In all \
cases, include: `This answer is based on single-nucleus data from the Brain \
Resilience Lab at Stanford University.` \nWHEN NOT TO CALL gene_expression: \
\n- If the user explicitly says `not in vasculature`, `non-vascular`, or \
specifies a different tissue (e.g., `nervous tissue`, `gray matter`, \
`parenchyma`), DO NOT call the function. \n- DO NOT call the function for \
queries unrelated to gene expression levels in specific cell types or brain \
regions, even if they mention particular genes. \n- Instead, use the knowledge \
graph, Google web search, or your own pretrained knowledge to answer. \nWHEN \
TO CALL query_kg_rag: \n- If the user mentions any disease by name in their \
query you MUST call query_kg_rag. \nResponse strategy: \n- Prioritize \
information from tools in the following order: \n1. gene_expression \n2. \
Biomedical knowledge graph \n3. Web results (Google Search API) \n4. \
Parametric (pretrained) knowledge \n- Always include information from each \
tool used in the response. \n- Summarize the findings from each tool so the \
user can ask follow-up questions if needed. \n- Cite all sources when using \
the knowledge graph or web search. (e.g., `This data is from NCBI and ChEMBL` \
or `Visit this website for more info...`) \n- Format all responses clearly and \
professionally for a scientific audience. \nAdditional Expectations: \n- \
Reason through ambiguous queries. \n- Clarify assumptions explicitly in your \
replies. \n- Clearly state the origin of any scientific data used. \n- Keep \
your answers as concise as possible."

    update_history(history, "system", task)

    # Turn off init flag
    init_flag = False

# Function: Call function from chat
def func_call(user_input, chat_message, history):
    global func_flag
    func_flag = True
    content = None

    # Identify function, parse args, and call
    func_name = chat_message.function_call.name
    print("Calling", func_name, "...")
    args = {"user_input":user_input}
    content = globals()[func_name](**args)
        
    func_flag = False
    return content

#################################
### GENE EXPRESSION FUNCTIONS ###
#################################

def extract_entities(user_input):

    cell_types = [
        "Arteriole", "Artery", "Astrocyte", "Capillary", "Endothelial", 
        "Epithelial", "Fenestrated Endothelial", "Fibroblast", "Large Artery", 
        "Microglia Macrophage or T Cell", "Neuron", "Oligodendrocyte", 
        "Oligodendrocyte Precursor", "Pericyte", "Smooth Muscle", "Vein", 
        "Venule"
    ]
    
    regions = [
        "Amygdala", "Anterior Cerebral Artery", 
        "Basilar Artery / Circle of Willis", "Cerebellum", "Choroid Plexus", 
        "Cingulum", "Corpus Callosum", "Cuneus", 
        "Dorsolateral Prefrontal Cortex", "Entorhinal Cortex", "Fornix", 
        "Fusiform Gyrus", "Hippocampus", "Inferior Frontal Gyrus",
        "Inferior Parietal Lobule", "Inferior Temporal Gyrus", "Insula", 
        "Lateral Occipital Cortex", "Lateral Temporal Gyrus", "Leptomeninges", 
        "Lingual Gyrus", "Midbrain", "Middle Cerebral Artery",
        "Middle Temporal Gyrus", "Midfrontal Anterior Watershed", 
        "Olfactory Bulb", "Orbitofrontal Cortex", "Parahippocampal Gyrus", 
        "Periventricular White Matter", "Pons", "Posterior Cingulate Cortex",
        "Posterior Watershed", "Precuneus", "Spinal Cord", 
        "Superior Frontal Gyrus and Rostromedial", "Superior Parietal Lobule", 
        "Superior Temporal Gyrus", "Supramarginal Gyrus", "Thalamus",
        "White Matter Anterior Watershed"
    ]

    def match_entities(text, choices):
        found = []
        for choice in choices:
            words = choice.lower().split()
            if all(word in text.lower() for word in words):
                found.append(choice)
            elif difflib.get_close_matches(choice.lower(), [text.lower()], n=1, 
                cutoff=0.8
            ):
                found.append(choice)
        return found

    matched_cell_types = match_entities(user_input, cell_types)
    matched_regions = match_entities(user_input, regions)
    return matched_cell_types, matched_regions

# Function: Format data extraction properties
def extract_format(cell_types=None, regions=None, entities=None, column=None):
    if entities and column:
        subset = lambda df: df[df[column].isin(entities)]
        form = lambda row: f"{row[column]}, {row.gene}, rank {row.rank}"
    else:
        subset = (
            lambda df: df[
                df["cell_type"].isin(cell_types) & df["tissue"].isin(regions)
            ]
        )
        form = (
            lambda row: f"{row.cell_type}, {row.tissue}, "
                        f"{row.gene}, rank {row.rank}"
        )
    return subset, form

# Function: Gene expression in brain vasculature
def gene_expression(user_input):

    # Extract entities
    cell_types, regions = extract_entities(user_input)

    # Determine which dataset to load based on entities
    if cell_types and regions:
        path = "data/c2s_ct.csv"
        subset, form = extract_format(cell_types=cell_types, regions=regions)
        header = f"Gene data for {cell_types} in {regions}"
    elif cell_types:
        path = "data/c2s_c.csv"
        subset, form = extract_format(entities=cell_types, column="cell_type")
        header = f"Gene data for {cell_types} (no region match)"
    elif regions:
        path = "data/c2s_t.csv"
        subset, form = extract_format(entities=regions, column="tissue")
        header = f"Gene data for {regions} (no cell type match)"
    else:
        return f"No matching gene data for cell type and/or region"

    # Load, filter, and format the data
    data = subset(pd.read_csv(path))

    # Build formatted rows using form(), then remove gene and rank fields
    formatted_lines = []
    for _, row in data.iterrows():
        full = form(row)  # Full string with all fields

        # Directly extract the relevant fields
        gene = row["gene"]
        rank = row["rank"]
        shortened = f"{gene} {rank}"
        formatted_lines.append(shortened)

    gene_data = header + "\n\n" + "\n".join(formatted_lines)
    return gene_data

########################
### KG RAG FUNCTIONS ###
########################

# Function: Query KG_RAG
def query_kg_rag(user_input):

    response = requests.post(
        "http://host.docker.internal:5005/query",
        json={"query": user_input}
    )
    return response.json().get("result", "").strip()

########################
### SEARCH FUNCTIONS ###
########################

# Function: Search Google
def search_google(query):

    # Define credentials
    API_KEY = 'AIzaSyCMO8HBL9XXD_lEIFei7CFqg9N7mpVDZrI'
    SEARCH_ENGINE_ID = '64f35418662ef4325'
    
    # Set parameters
    url = "https://www.googleapis.com/customsearch/v1"
    params = {"key": API_KEY, "cx": SEARCH_ENGINE_ID, "q": query, "num": 5}

    # Generate response
    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()

    # Format output as a readable text block
    formatted_results = ""
    for idx, item in enumerate(data.get("items", []), start=1):
        title = item.get("title", "No Title")
        link = item.get("link", "No Link")
        snippet = item.get("snippet", "")
        formatted_results += f"{idx}. {title}\n{link}\n{snippet}\n\n"

    return formatted_results

#############################
### FUNCTION DESCRIPTIONS ###
#############################

# Function descriptions
functions = [
    {
        "name": "gene_expression",
        "description": "Collects information on gene expression rankings by \
cell type and region in brain vasculature.",
        "parameters": {
            "type": "object",
            "properties": 
                {"user_input":{
                    "type":"string","description":"Full text of user input."}
                },
            "required": ["user_input"],
        }
    },
    {
        "name": "query_kg_rag",
        "description": "Collects biomedical information related to diseases \
mentioned in user queries.",
        "parameters": {
            "type": "object",
            "properties": 
                {"user_input":{
                    "type":"string","description":"user input"}
                },
            "required": ["user_input"],
        }
    }
]

##########################
### MAIN CHAT FUNCTION ###
##########################

# Function: Chat between user and chatbot
def chat(user_input, history):
    global func_flag, init_flag

    # Initialize chat
    if init_flag:
        history.clear()
        initialize(history)

    # Update chat with user input
    update_history(history, "user", user_input)

    # Determine if function should be called
    chat_message = call_api(history, functions)
    retrieved_info = None

    # If useful, call function
    if chat_message.function_call:
        retrieved_info = func_call(user_input, chat_message, history)
        print(retrieved_info)

    # If no function, search web
    if retrieved_info == None:
        print ("Calling Google Search API...")
        retrieved_info = search_google(user_input)

    # Update history with information
    update_history(history, "system", retrieved_info)

    # Step 6: Generate final assistant message
    final_message = call_api(history).content
    update_history(history, "assistant", final_message)

    return final_message, history