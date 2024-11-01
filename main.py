from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
from dotenv import load_dotenv
import pandas as pd
import json
from openai import OpenAI
import sys
from io import StringIO
import re

# Load environment variables from .env file
load_dotenv()

app = FastAPI()

dataset_columns = None
data_sample = None
df = None

tools = [
    {
        "type": "function",
        "function": {
            "name": "analyze_data",
            "description": "Perform mathematical operations (such as averages/means, medians, modes, ranges, sums, and counts) and data analysis based on the user query. This tool is used when the user asks for specific calculations, aggregations, or comparisons between numerical data points in the dataset.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The analysis query to execute on the dataset."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "construct_spec_prompt",
            "description": "Create a Vega-Lite specification based on the user query. This tool is used when the user requests visualizations or chart specifications based on relationships or comparisons between data columns (e.g., 'visualize [] vs []').",
            "parameters": {
                "type": "object",
                "properties": {
                    "columns": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "description": "The dataset columns available for generating the Vega-Lite specification."
                    },
                    "data_sample": {
                        "type": "object",
                        "description": "The uploaded data set for which to generate a Vega-Lite specification."
                    },
                    "user_query": {
                        "type": "string",
                        "description": "The query for which to generate a Vega-Lite specification."
                    }
                },
                "required": ["user_query"]
            }
        }
    }
]


dataset_columns = None
data_sample = None

# Mount the static directory
app.mount("/docs", StaticFiles(directory="docs"), name="docs")

origins = [
    "http://127.0.0.1:8001",  # Add the origin you want to allow
    "http://localhost:8001",
    "https://lmarfeo.github.io",
]
# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins, #["https://lmarfeo.github.io"],  # Adjust this to restrict allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load OpenAI API key from environment variable
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# Define request and response models
class QueryRequest(BaseModel):
    prompt: str

class QueryResponse(BaseModel):
    response: str

def check_query_relevance(user_query, columns):
    return f"""
    Determine if the following user query is relevant to the dataset provided.
    
    User query: '{user_query}'
    
    Dataset columns: {', '.join(columns)}

    If the user query DOES NOT RELATE to the data in the uploaded CSV file, return 'False'. If it does relate, return 'True'.

    Note: Synonyms for dataset words should also be considered relevant.

    Examples of user queries that DON'T pertain to data within a csv file:
    - 'Hi'
    - 'How are you?'

    Examples of user queries that DO pertain to data within a MOVIES.CSV file:
    - 'genre vs imdb rating'
    - 'visualize content rating'
    - 'average rotten tomatoes rating'
    """

# Sanitize input
def sanitize_input(query: str) -> str:
    query = re.sub(r"^(\s|`)*(?i:python)?\s*", "", query)
    query = re.sub(r"(\s|`)*$", "", query)
    return query

# Function to execute generated code
def execute_code(code: str, df: pd.DataFrame):
    old_stdout = sys.stdout
    sys.stdout = mystdout = StringIO()
    
    try:
        cleaned_command = sanitize_input(code)
        exec(cleaned_command, {"df": df})
        sys.stdout = old_stdout
        return mystdout.getvalue()
    except Exception as e:
        sys.stdout = old_stdout
        return repr(e)
    
def analyze_data(query: str, df):
    # Define the prompt to guide OpenAI's code generation
    prompt = f"""
    Write Python code to perform data analysis based on this query: '{query}'. 
    The code should analyze {df}, a DataFrame, and output the result using print statements for each finding.
    Only return Python code as your answer.
    """
    
    # Call OpenAI API to generate code
    try:
        analysis_response = query(prompt, system_prompt="Generate Python code for data analysis", tools=None, tool_map=None)
        # Assume the response contains the generated code
        code = analysis_response.strip()  # Get the generated code
        result = execute_code(code, df)  # Execute the generated code with the DataFrame
        return result  # Return the output from the executed code
    except Exception as e:
        return f"Error analyzing data: {str(e)}"  

def get_data_type(sample, column_name):
    # Get the first non-None value in the sample for the specified column
    for entry in sample:
        value = entry.get(column_name)
        if value is not None:
            # Check if the value is an integer or float for quantitative types
            if isinstance(value, (int, float)):
                return "quantitative"
            # Otherwise, treat it as nominal
            return "nominal"
    return "nominal"  # Default to nominal if no valid value is found

def construct_spec_prompt(columns, data_sample, user_query):
    return f"""
    You are a data visualization assistant specialized in creating Vega-Lite charts.

    Dataset Information:
    - Columns: {columns}
    - Full Dataset (required for accurate visualization): {json.dumps(data_sample)}

    User Question: "{user_query}"

    Please use all provided information, including the full dataset, to construct an accurate Vega-Lite specification.

    Generate a function call with the following parameters:
    - `user_query`: The question or visualization request from the user.
    - `columns`: An array containing all available columns in the dataset.
    - `data_sample`: A JSON object containing a small sample of the dataset.

    Your task is to create a valid Vega-Lite JSON specification that directly answers the user's question.

    If the user asks to visualize a specific column, do not plot it against itself. 
    Instead, select another column that is most appropriate to pair with it based on the dataset.
    Example:
    - If the user query is "visualize mpg", create a scatterplot with mpg on one axis and another quantitative column on the other axis (eg. choose a variable like "horsepower", "weight", or "displacement" for the other axis, not mpg vs mpg).
    
    Please ensure that your output is a complete Vega-Lite JSON specification ONLY do not include any other descriptions or details outside of the JSON specification. 

    IMPORTANT:
    1. Ensure that the output is a valid JSON Vega-Lite specification, formatted correctly.
    2. Use the appropriate chart type (e.g., bar chart, pie chart, scatter plot) based on the type of data being visualized and the user query.
        a. If the user query constains the word "visualize" the chart type used must be a scatter plot
    3. The chart should include appropriate color coding and a legend.
    4. Make sure the chart axes are labeled clearly, and include any relevant titles.
    5. If you detect any issues with the Vega-Lite JSON, fix them automatically before responding.
    6. Double-check that the output does not contain links to images or any non-chart information.
    7. DO NOT bracket the JSON specification with ''

    After constructing the JSON specification, carefully review it to ensure that it is well-structured and free of errors. Make sure the JSON format is correct, and all required fields are present and valid.
    UNDER NO CIRCUMSTANCES bracket your JSON specification like so: json ``` [JSON SPEC HERE] ```
    Here are a few examples of valid Vega-Lite specifications:

    Example 1:
    {{
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "data": {{
            "values": [
                {{"category":"A", "group": "x", "value":0.1}},
                {{"category":"A", "group": "y", "value":0.6}},
                {{"category":"A", "group": "z", "value":0.9}},
                {{"category":"B", "group": "x", "value":0.7}},
                {{"category":"B", "group": "y", "value":0.2}},
                {{"category":"B", "group": "z", "value":1.1}},
                {{"category":"C", "group": "x", "value":0.6}},
                {{"category":"C", "group": "y", "value":0.1}},
                {{"category":"C", "group": "z", "value":0.2}}
            ]
        }},
        "mark": "bar",
        "encoding": {{
            "x": {{"field": "category"}},
            "y": {{"field": "value", "type": "quantitative"}},
            "xOffset": {{"field": "group"}},
            "color": {{"field": "group"}}
        }}
    }}
    
    Example 2:
    {{
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "data": {{
            "values": [
                {{"city": "New York", "population": 8000000}},
                {{"city": "Los Angeles", "population": 4000000}},
                {{"city": "Chicago", "population": 2700000}}
            ]
        }},
        "mark": "bar",
        "encoding": {{
            "x": {{"field": "city"}},
            "y": {{"field": "population", "type": "quantitative"}}
        }}
    }}

    """

def construct_description_prompt(vega_spec):
    return f"""
    Given the following Vega-Lite specification, please provide a short description explaining what it represents and any important insights.

    Vega-Lite Specification:
    {json.dumps(vega_spec)}

    Here are a few example descriptions:
    'This line chart illustrates the growth of the world population over the years, highlighting a steady increase.',
    'This pie chart depicts the sales distribution among different products, allowing for easy comparison of their market shares.'
    """

@app.post("/upload_csv")
async def upload_csv(csv_file: UploadFile):
    global dataset_columns, data_sample
    contents = await csv_file.read()
    df = pd.read_csv(pd.io.common.BytesIO(contents))

    dataset_columns = df.columns.tolist()
    data_sample = df.sample(n=100).to_dict(orient='records')
    return {"message": "CSV uploaded successfully"}

# Define the tool map for referencing functions
tool_map = {
    "construct_spec_prompt": construct_spec_prompt, 
    "analyze_data": analyze_data,  
}
def prepare_function_args(tool_name, args):
    global data_sample  # Make sure data_sample is accessible here if it's needed

    if tool_name == "analyze_data":
        if 'query' not in args:
            raise ValueError("Missing required 'query' parameter in analyze_data call")
        if data_sample is None:
            raise ValueError("Data sample is missing; upload a dataset first.")
        # Convert data_sample back to a DataFrame for analysis
        df = pd.DataFrame(data_sample)
        return {"query": args["query"], "df": df.to_dict(orient="records")}
        
    elif tool_name == "construct_spec_prompt":
        if 'user_query' not in args:
            raise ValueError("Missing required 'user_query' parameter in construct_spec_prompt call")
        
        columns = args.get("columns", dataset_columns)
        data_sample = args.get("data_sample", data_sample)
        
        return {
            "user_query": args["user_query"],
            "columns": columns,
            "data_sample": data_sample,
        }
    else:
        raise ValueError(f"Unknown tool: {tool_name}")

@app.post("/query")
async def query_openai(request: QueryRequest):
    global dataset_columns, data_sample

    if not dataset_columns or not data_sample:
        return QueryResponse(response="Please upload a dataset first.")

    user_query = request.prompt
    
    relevance_prompt = check_query_relevance(user_query, dataset_columns)
    
    # Send the relevance check prompt to the OpenAI API
    relevance_response = query(relevance_prompt, system_prompt="Evaluate relevance", tools=None, tool_map=None)

    if relevance_response.strip().lower() != 'true':
        return QueryResponse(response=f"The question '{user_query}' is not relevant to the dataset.")
    
    system_prompt = "You are a data assistant. You can analyze data or create Vega-Lite charts."
    
    response_content = query(user_query, system_prompt, tools, tool_map)

    if function_to_call.__name__ == "construct_spec_prompt":

        try:
            response_json = json.loads(response_content)  # This assumes response_content is a string
        except json.JSONDecodeError:
            return JSONResponse(content={"error": "Failed to parse response from OpenAI."}, status_code=500)

        description_prompt = construct_description_prompt(response_json)

        # Send the description prompt to OpenAI
        description_response = query(description_prompt, system_prompt="Generate a chart description", tools=None, tool_map=None)

        # Return the parsed JSON response along with the generated description
        return JSONResponse(content={
            "specification": response_json,
            "description": description_response.strip()
        })
    elif function_to_call.__name__ == "analyze_data":
        try:
            # This response_content would be the result of the data analysis as a direct answer
            result = function_to_call(user_query, df)  # Use df instead of your_dataframe
            return QueryResponse(response=result)
        except Exception as e:
            return QueryResponse(response=f"Error analyzing data: {str(e)}")

    

def truncate_string(string: str, max_length: int = 100) -> str:
    """Truncate the string to a maximum length and append '...' if truncated."""
    if len(string) > max_length:
        return string[:max_length] + "..."
    return string

def query(question, system_prompt, tools, tool_map, max_iterations=10):
    global function_to_call
    messages = [{"role": "system", "content": system_prompt}]
    messages.append({"role": "user", "content": question})
    
    # Proceed if query is relevant
    i = 0
    while i < max_iterations:
        i += 1
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.0,
            messages=messages,
            tools=tools
        )
        
        if response.choices[0].message.content is not None:
            print_red(response.choices[0].message.content)

        # Check if it's not a function call
        if response.choices[0].message.tool_calls is None:
            break

        # Process function calls
        messages.append(response.choices[0].message)
        print(response.choices[0].message.tool_calls)
        for tool_call in response.choices[0].message.tool_calls:
            print_blue("calling:", tool_call.function.name, "with", tool_call.function.arguments)
            # Prepare and call the function
            arguments = prepare_function_args(tool_call.function.name, json.loads(tool_call.function.arguments))
            print("Parsed arguments:", arguments)
            function_to_call = tool_map[tool_call.function.name]
            result = function_to_call(**arguments)
            print("THIS IS THE RESULT: ", function_to_call)

            # Create a message with the function call result
            result_content = json.dumps({**arguments, "result": result})
            function_call_result_message = {
                "role": "tool",
                "content": result_content,
                "tool_call_id": tool_call.id,
            }
            print("Function result:", result_content)
            
            truncResult = truncate_string(result_content)
            print_blue("action result:", truncResult)

            messages.append(function_call_result_message)
        
        # Check iteration limit
        if i == max_iterations and response.choices[0].message.tool_calls is not None:
            print_red("Max iterations reached")
            return "The tool agent could not complete the task in the given time. Please try again."

    print(response.choices[0].message.content)
    return response.choices[0].message.content


# print msg in red, accept multiple strings like print statement
def print_red(*strings):
    print("\033[91m" + " ".join(strings) + "\033[0m")


# print msg in blue, , accept multiple strings like print statement
def print_blue(*strings):
    print("\033[94m" + " ".join(strings) + "\033[0m")