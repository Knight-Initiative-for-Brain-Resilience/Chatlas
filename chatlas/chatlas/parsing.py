#########################
### ENVIRONMENT SETUP ###
#########################

# Import modules
import re

from typing import Dict

########################
### HELPER FUNCTIONS ###
########################

# Function: Extract keywords from query
def parse_query(query: str) -> Dict:

    parsed = {}

    # Can be replaced with spaCy + biomedical NER
    # What if the user asks multiple questions in one query?
    # What if the query is basic, e.g. what is this gene?
    if "drug" in query:
        parsed["query_type"] = "drug_targeting"
    if "gene" in query:
        parsed["query_type"] = "gene_function"

    # Extract anatomical regions or structures
    if "cerebellum" in query.lower():
        parsed["region"] = "cerebellum"
    if "vasculature" in query.lower():
        parsed["target_structure"] = "vasculature"

    return parsed
        
###########################
### MAIN PARSE FUNCTION ###
###########################