#########################
### ENVIRONMENT SETUP ###
#########################

# Import modules
import json
import openai
import os
import pandas as pd
import requests
import warnings
from .gemini import browse_web

# Set gloabl variables
global func_flag
global init_flag

func_flag = False
init_flag = True

# Set API key
openai.api_key = os.getenv("OPENAI_API_KEY")

# Supress warnings
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

########################
### HELPER FUNCTIONS ###
########################

# Function: Get File
def get_file(path, ext):
    for root, _, files in os.walk(path):
        for file in files:
            if file.endswith(ext):
                return os.path.join(root, file)
    return None

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
    task = task = "You are a neuroscience research assistant. You can answer \
scientific questions using multiple resources. You should reference the history \
of the conversation and make inferences based on it when you respond (e.g., assume \
a user is refering to the same cell type as they did most recently if unspecified). \
You also have access to the following tools: \n\
1. `gene_expression`: This function provides gene expression and protein prevalence data for specific \
**cell types and regions** in brain vasculature, using single-nucleus RNA \
sequencing (snRNA-seq) from the **Brain Resilience Laboratory at Stanford \
University**. This dataset covers gene expression and protein prevalence in several cell types \
**within the vasculature** of specific brain regions. \n\
2. A **biomedical knowledge graph** based on SPOKE from UCSF, which includes \
curated scientific knowledge about molecular and disease biology. \n\
3. A **Gemini API** for performing web search on biomedical topics. \n\
4. Your own scientific knowledge from your pre-training process. \n\n\
WHEN TO CALL `gene_expression`: \n\
- If the user asks about gene expression or protein prevalence in a **cell type and/or brain \
region**, and does NOT specify a tissue type, ASSUME they mean **brain \
vasculature** and call the function. \n\
- If the user explicitly mentions vasculature (e.g., 'in vasculature', \
'vascular tissue', 'blood vessels'), call the function. \n\
- In the first case, include a note such as: 'Since you specified cell type \
and brain region but did not mention tissue type, I’ve assumed brain \
vasculature. If they mention brain vasculature, don't include a note. \n\
- In both cases, include a note such as: 'This answer is based on \
single-nucleus data from the Brain Resilience Lab at Stanford University.' \n\n\
WHEN **NOT** TO CALL `gene_expression`: \n\
- If the user explicitly says 'not in vasculature', 'non-vascular', or \
specifies a different tissue (e.g., 'nervous tissue', 'gray matter', \
parenchyma'), DO NOT call the function. \n\
- DO NOT call the function for any queries that are unrelated to gene \
expression levels in certain cell types or brain regions, even if they mention \
specific genes. \n\
- Use the knowledge graph, web search, or your own knowledge, to answer \
instead. \n\n\
HOW TO HANDLE DATA OUTPUT FROM `gene_expression`: \n\
- If the data from `gene_expression` only relates to a brain region, you MUST \
state in your response that the answer is for all cell types across the \
region. \
- If the data from `gene_expression` only relates to a cell type, you MUST \
state in your response that the answer is for that cell type across all \
regions. \n\
RESPONSE STRATEGY: \n\
- Prioritize information from tools in this order: \n\
    1. `gene_expression` \n\
    2. Biomedical knowledge graph \n\
    3. Web results \n\
    4. Parametric (internal) knowledge \n\
- You should include information from all of the tools used in each response. \
\n\
- Summarize the information from each tool so the user can ask follow up \
questions if desired. \n\
- Cite all sources when drawing from the knowledge graph or web search (e.g., \
'This data is from NCBI and ChEMBL', or 'Visit this website for more info...') \
\n\
- Format all outputs clearly and professionally for a scientific audience. \n\n\
You are expected to reason through ambiguous queries, clarify assumptions in \
your replies, and explicitly describe the origin of any scientific data used \
in your answers."

    update_history(history, "system", task)

    # Add research context
    path = get_file("media", ".txt")
    if path:
        with open(path, "r") as f:
            context = f.read()
            update_history(history, "user", context)

    # Turn off init flag
    init_flag = False

# Function: Call function from chat
def func_call(chat_message, history):
    global func_flag
    func_flag = True
    content = None

    try:
        # Identify function, parse args, and call
        print("Calling gene expression function...")
        func_name = chat_message.function_call.name
        args = json.loads(chat_message.function_call.arguments or '{}')
        content = globals()[func_name](**args)

    except KeyError as e:
        print(f"Function '{func_name}' not found: {e}")
        content = f"Function '{func_name}' not found."

    # Turn off func flag
    finally:
        func_flag = False

    return content

########################
### KG RAG FUNCTIONS ###
########################

# Function: Query KG_RAG
def query_kg_rag(user_input):
    try:
        print("Querying knowledge graph...")
        response = requests.post(
            "http://host.docker.internal:5005/query",
            json={"query": user_input}
        )
        if response.status_code == 200:
            return response.json().get("result", "").strip()

        error_info = response.json().get("error", "Unknown error")
        return f"[KG_RAG Error {response.status_code}] {error_info}"

    except requests.exceptions.RequestException as e:
        return f"[KG_RAG Request Exception: {str(e)}]"

    except Exception as e:
        return f"[KG_RAG Exception: {str(e)}]"

########################################
### BRAIN VASCULATURE DATA FUNCTIONS ###
########################################

# Function: Extract cell type and tissue from user input
def extract_entities(user_input):

    # Initialize cell types and tissues
    cell_types = None
    tissues = None

    task = "You are an assistant that extracts entity mentions from user \
input related to gene expression in brain vasculature. You will receive a \
list of valid cell types and a list of valid tissues. Your task is to \
identify any of these mentioned in the user query, and return them in JSON \
format with two keys: 'cell_types' and 'tissues'. Err on the side of returning \
matches that are close but not exact. Return the matched entities from the \
official cell type and tissue lists. Return an empty list for either key if \
nothing is found.\n\n \
CELL TYPES: Astrocyte, Capillary Type 1, Capillary Type 2, Capillary Type 3, \
Endothelial to Mesenchymal Transition Type 1, Endothelial to Mesenchymal \
Transition Type 2, Epithelial Cell Type 1, Epithelial Cell Type 2, Epithelial \
Cell Type 3, Fenestrated Endothelial Cell, Fibroblast Type 1, Fibroblast Type \
2, Fibroblast Type 3, Fibroblast Type 4, Fibroblast Type 5, Large Artery, \
Microglia Macrophage or T Cell, Neuron, Oligodendrocyte Precursor Cell, \
Oligodendrocyte, Pericyte Type 1, Pericyte Type 2, Pericyte Type 3, Smooth \
Muscle Cell Type 1, Smooth Muscle Cell Type 2, Smooth Muscle Cell Type 3, \
Smooth Muscle Cell Type 4, Vein, Venule \n\
TISSUES: Hippocampus, Amygdala, Lingual Gyrus, Insula, Posterior Cingulate \
Cortex, Inferior Parietal Lobule, Orbitofrontal Cortex, Superior Temporal \
Gyrus, Inferior Temporal Gyrus, Lateral Temporal Gyrus, Inferior Frontal \
Gyrus, Cuneus, Anterior Cingulate Cortex, Lateral Occipital Cortex, Superior \
Parietal Lobule, Superior Frontal Gyrus and Rostromedial, Dorsolateral \
Prefrontal Cortex, Pons, Cerebellum, Thalamus, Spinal Cord, Midbrain, \
Midfrontal Anterior Watershed, White Matter Anterior Watershed, Posterior \
Watershed, Periventricular White Matter, Cingulum, Fornix, Corpus Callosum, \
Parahippocampal Gyrus, Entorhinal Cortex, Supramarginal Gyrus, Fusiform Gyrus, \
Precuneus, Middle Temporal Gyrus, Olfactory Bulb, Choroid Plexus, \
Leptomeninges, Middle Cerebral Artery, Anterior Cerebral Artery, Basilar \
Artery / Circle of Willis, Arteriole, Artery"

    messages = messages=[
            {"role": "system", "content": task},
            {"role": "user", "content": user_input}
        ]
    data = json.loads(call_api(messages).content)

    if len(data["cell_types"]) > 0:
        cell_types = data["cell_types"]
    if len(data["tissues"]) > 0:
        tissues = data["tissues"]

    return cell_types, tissues

# Function: Format data extraction properties
def extract_format(cell_types=None, tissues=None, entities=None, column=None):
    if entities and column:
        subset = lambda df: df[df[column].isin(entities)]
        form = lambda row: f"{row[column]}, {row.gene}, rank {row.rank}"
    else:
        subset = (
            lambda df: df[
                df["cell_type"].isin(cell_types) & df["tissue"].isin(tissues)
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
    cell_types, tissues = extract_entities(user_input)

    # Determine which dataset to load based on entities
    if cell_types and tissues:
        path = "data/c2s_ct.csv"
        subset, form = extract_format(cell_types=cell_types, tissues=tissues)
        header = f"Gene data for {cell_types} in {tissues}"
    elif cell_types:
        path = "data/c2s_c.csv"
        subset, form = extract_format(entities=cell_types, column="cell_type")
        header = f"Gene data for {cell_types} (no tissue match - showing all regions)"
    elif tissues:
        path = "data/c2s_t.csv"
        subset, form = extract_format(entities=tissues, column="tissue")
        header = f"Gene data for {tissues} (no cell type match - showing all regions)"
    else:
        return f"No matching gene data for cell type and/or region in user input"

    # Load, filter, and format the data
    data = subset(pd.read_csv(path))
    gene_data = header + "\n\n" + "\n".join([form(row) for _, row in data.iterrows()])

    return gene_data

#############################
### FUNCTION DESCRIPTIONS ###
#############################

# Function descriptions
functions = [
    {
        "name": "gene_expression",
        "description": "Collects information on gene expression rankings by \
cell type and tissue in brain vasculature.",
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
    function_response = None

    # If useful, call function
    if chat_message.function_call:
        function_response = func_call(chat_message, history)

    # Query the knowledge graph and do web search
    kg_response = query_kg_rag(user_input)
    web_results = browse_web(user_input)

    # Combine tool output
    summary_parts = []
    if function_response:
        summary_parts.append(f"Function output: {function_response}")
    summary_parts.append(f"Knowledge graph: {kg_response}")
    summary_parts.append(f"Web search: {web_results}")
    combined_summary = "Here's relevant information from tools:\n" + "\n\n".join(summary_parts)
    
    # Update history with information
    update_history(history, "system", combined_summary)

    # Step 6: Generate final assistant message
    final_message = call_api(history).content
    update_history(history, "assistant", final_message)

    return final_message, history