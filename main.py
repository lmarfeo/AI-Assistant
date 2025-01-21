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

# Load environment variables from .env file
load_dotenv()

app = FastAPI()

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
print("Loaded API Key:", os.environ.get("OPENAI_API_KEY"))

# Define request and response models
class QueryRequest(BaseModel):
    prompt: str

class QueryResponse(BaseModel):
    response: str

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

def construct_spec_prompt(columns, sample, user_query):
    return f"""
    You are a data visualization assistant specialized in creating Vega-Lite charts.

    Dataset Information:
    - Columns: {columns}
    - Full Dataset: {json.dumps(data_sample)}

    User Question: "{user_query}"

    Your task is to create a valid Vega-Lite JSON specification that directly answers the user's question. If the user query DOES NOT RELATE to the data in the uploaded csv file or contain any of the following words in {columns} send the following response: "The question '{user_query}' is not relevant to the dataset, which contains information about [ENTER DESCRIPOR HERE] and [ENTER DECRIPTOR HERE]. '{user_query}' does not pertain to any data analyisis or visualization task."
    
    Examples of user queries that don't pertain to data within a csv file:
    - 'Hi'
    - 'How are you?'

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
    print("Uploading CSV...")  # Debug statement
    # Read the CSV file
    contents = await csv_file.read()
    df = pd.read_csv(pd.io.common.BytesIO(contents))

    # Set dataset_columns and data_sample
    dataset_columns = df.columns.tolist()
    data_sample = df.sample(n=100).to_dict(orient='records')
    print(f"Dataset columns: {dataset_columns}")  # Debug statement
    print(f"Data sample: {data_sample}")  # Debug statement
    return {"message": "CSV uploaded successfully"}

@app.post("/query", response_model=QueryResponse)
async def query_openai(request: QueryRequest):
    global dataset_columns, data_sample
    print("Received query request...")  # Debug statement
    print(f"Current dataset_columns: {dataset_columns}")  # Debug statement
    print(f"Current data_sample: {data_sample}")  # Debug statement

    if not dataset_columns or not data_sample:
        print("No dataset uploaded.")  # Debug statement
        return QueryResponse(response="Please upload a dataset first.")

    # Construct the prompt for Vega-Lite specification
    spec_prompt = construct_spec_prompt(dataset_columns, data_sample, request.prompt)
    print(f"Specification Prompt: {spec_prompt}")  # Debug statement

    while True:
        try:
            spec_response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a data visualization assistant specialized in creating Vega-Lite charts."},
                    {"role": "user", "content": spec_prompt}
                ]
            )
            vega_spec = spec_response.choices[0].message.content.strip()
            print("Vega-Lite Specification Response:", repr(vega_spec))  # Debug statement

            # Remove surrounding single quotes if they exist
            if vega_spec.startswith("'") and vega_spec.endswith("'"):
                vega_spec = vega_spec[1:-1]

            # Replace single quotes with double quotes
            vega_spec = vega_spec.replace("'", '"')

            # Check if the response indicates irrelevance to the dataset
            if "not relevant" in vega_spec.lower():
                # Return the irrelevance message without parsing it as JSON
                return QueryResponse(response=vega_spec)

            # Try to parse the Vega-Lite specification as JSON
            try:
                vega_spec_json = json.loads(vega_spec)
                print("Valid Vega-Lite Specification received.")  # Debug statement
                break  # Exit the loop if parsing is successful
            except json.JSONDecodeError as e:
                print(f"JSONDecodeError: {str(e)}")
                # Adjust the prompt to ask for a correction based on the error
                spec_prompt += f"\n\nNote: There was a JSON parsing error: {str(e)}. Please correct the Vega-Lite specification."
                continue  # Continue the loop to get a new specification

        except Exception as e:
            return QueryResponse(response=f"Error calling OpenAI API: {str(e)}")

    # Generate description based on the valid Vega-Lite specification
    description_prompt = construct_description_prompt(vega_spec_json)
    print(f"Description Prompt: {description_prompt}")  # Debug statement

    try:
        description_response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that provides descriptions for data visualizations."},
                {"role": "user", "content": description_prompt}
            ]
        )
        description = description_response.choices[0].message.content.strip()
        print("Description Response:", repr(description))  # Debug statement
    except Exception as e:
        print(f"Failed to generate description: {str(e)}")
        description = "Failed to generate description."

    return JSONResponse(content={"specification": vega_spec_json, "description": description})