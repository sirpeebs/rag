import os
import sqlite3
import openai
import numpy as np
import chromadb
from chromadb.utils import embedding_functions
from flask import Flask, render_template, request, jsonify
from datetime import datetime
import json
import time

# Initialize Flask app
app = Flask(__name__)

# Initialize the OpenAI client with your API key
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
db_path = os.path.join(os.path.dirname(__file__), '..', 'masterData.sqlite3')

# Initialize ChromaDB for vector storage
CHROMA_PERSIST_DIR = os.path.join(os.path.dirname(__file__), 'vectordb')
openai_ef = embedding_functions.OpenAIEmbeddingFunction(
    api_key=os.getenv("OPENAI_API_KEY"),
    model_name="text-embedding-3-small"
)
chroma_client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)

# Create or get the collection for service reports
try:
    service_reports_collection = chroma_client.get_collection(
        name="service_reports", 
        embedding_function=openai_ef
    )
    print("Connected to existing ChromaDB collection")
except:
    service_reports_collection = chroma_client.create_collection(
        name="service_reports", 
        embedding_function=openai_ef
    )
    print("Created new ChromaDB collection")

def connect_database():
    try:
        conn = sqlite3.connect(db_path)
        return conn
    except Exception as e:
        print("Error connecting to database:", e)
        return None

def generate_embedding(text):
    """Generate an embedding vector for the given text using OpenAI's embedding model"""
    if not text:
        return None
    
    try:
        response = client.embeddings.create(
            input=text,
            model="text-embedding-3-small"
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"Error generating embedding: {e}")
        return None

def index_service_reports():
    """Index all service reports into the vector database"""
    conn = connect_database()
    if conn is None:
        return "Error connecting to database."
    
    cursor = conn.cursor()
    query = """
    SELECT 
        ServiceReport_id, 
        Model, 
        Serial, 
        WorkRequired, 
        ServicePerformed, 
        VerificationTest,
        Date
    FROM ServiceReports
    """
    cursor.execute(query)
    reports = cursor.fetchall()
    
    # Check if collection is already populated
    if service_reports_collection.count() >= len(reports):
        print(f"Collection already has {service_reports_collection.count()} reports")
        return
    
    # Clear existing data - FIX THE ERROR HERE
    # Instead of service_reports_collection.delete(where={})
    try:
        # Option 1: Delete all items without filtering
        service_reports_collection.delete(where=None)
    except Exception as e:
        try:
            # Option 2: If that fails, delete with a "match all" condition
            service_reports_collection.delete(where={"$and": [{"service_report_id": {"$exists": True}}]})
        except Exception as e2:
            print(f"Warning: Could not clear collection: {e2}. Will add to existing data.")
    
    # Prepare batches for efficient insertion
    ids = []
    texts = []
    metadatas = []
    
    print(f"Indexing {len(reports)} service reports...")
    
    for report in reports:
        report_id = str(report[0])
        model = report[1] or ""
        serial = report[2] or ""
        work_required = report[3] or ""
        service_performed = report[4] or ""
        verification = report[5] or ""
        date = report[6] or ""
        
        # Create a combined text for embedding
        combined_text = f"Model: {model}\nIssue: {work_required}\nSolution: {service_performed}\nVerification: {verification}"
        
        # Skip if text is too short
        if len(combined_text) < 10:
            continue
        
        ids.append(report_id)
        texts.append(combined_text)
        metadatas.append({
            "model": model,
            "serial": serial,
            "date": date,
            "service_report_id": report_id
        })
        
        # Add in batches of 100
        if len(ids) >= 100:
            service_reports_collection.add(
                ids=ids,
                documents=texts,
                metadatas=metadatas
            )
            ids = []
            texts = []
            metadatas = []
            print(f"Added batch of 100 reports, collection now has {service_reports_collection.count()} reports")
    
    # Add any remaining reports
    if ids:
        service_reports_collection.add(
            ids=ids,
            documents=texts,
            metadatas=metadatas
        )
    
    conn.close()
    print(f"Finished indexing. Collection now has {service_reports_collection.count()} reports")

def get_machine_history(conn, model=None, serial=None):
    cursor = conn.cursor()
    
    # Base query joining all relevant tables
    query = """
    SELECT DISTINCT
        m.Serial,
        m.Model,
        m.Install_Date,
        sr.ServiceReport_id,
        sr.Date,
        sr.WorkRequired,
        sr.ServicePerformed,
        sr.VerificationTest,
        sr.Failure_Type,
        sr.ServiceType
    FROM Machines m
    LEFT JOIN ServiceReports sr ON m.Serial = sr.Serial
    WHERE 1=1
    """
    
    params = []
    if model:
        query += " AND m.Model LIKE ?"
        params.append(f"%{model}%")
    if serial:
        query += " AND m.Serial = ?"
        params.append(serial)
    
    query += " ORDER BY sr.Date DESC LIMIT 10"  # Get most recent reports
    
    cursor.execute(query, params)
    return cursor.fetchall()

def get_related_parts(conn, service_report_id):
    cursor = conn.cursor()
    query = """
    SELECT PartNumber, Description
    FROM ServiceReportParts
    WHERE ServiceReport_id = ?
    """
    cursor.execute(query, (service_report_id,))
    return cursor.fetchall()

def get_common_issues(conn, model):
    """Get most common issues and solutions for a specific model"""
    cursor = conn.cursor()
    query = """
    SELECT WorkRequired, ServicePerformed, COUNT(*) as frequency
    FROM ServiceReports
    WHERE Model LIKE ?
    GROUP BY WorkRequired, ServicePerformed
    ORDER BY frequency DESC
    LIMIT 3
    """
    cursor.execute(query, (f"%{model}%",))
    return cursor.fetchall()

def get_service_report_by_id(conn, report_id):
    """Get a specific service report by ID"""
    cursor = conn.cursor()
    query = """
    SELECT 
        ServiceReport_id,
        Date,
        Model,
        Serial,
        WorkRequired,
        ServicePerformed,
        VerificationTest
    FROM ServiceReports
    WHERE ServiceReport_id = ?
    """
    cursor.execute(query, (report_id,))
    return cursor.fetchone()

def build_context(model=None, serial=None):
    conn = connect_database()
    if conn is None:
        return "Error connecting to database."
    
    machine_history = get_machine_history(conn, model, serial)
    if not machine_history:
        conn.close()
        return "No service history found for the specified machine."
    
    context = "Machine Service History Analysis:\n\n"
    
    # Add machine details
    machine_info = machine_history[0]  # First row has the machine info
    context += f"Machine Details:\n"
    context += f"Model: {machine_info[1]}\n"
    context += f"Serial: {machine_info[0]}\n"
    context += f"Installation Date: {machine_info[2]}\n\n"
    
    # Add recent service history
    context += "Recent Service History:\n"
    for record in machine_history:
        if record[3]:  # If there's a service report
            context += f"\nService Report {record[3]} ({record[4]}):\n"
            if record[5]:  # WorkRequired
                context += f"Issue: {record[5][:200]}\n"
            if record[6]:  # ServicePerformed
                context += f"Solution: {record[6][:200]}\n"
            if record[7]:  # VerificationTest
                context += f"Verification: {record[7][:200]}\n"
            
            # Get parts used
            parts = get_related_parts(conn, record[3])
            if parts:
                context += "Parts Used: " + ", ".join([f"{p[0]} ({p[1]})" for p in parts[:3]]) + "\n"
    
    # Add common issues for this model
    common_issues = get_common_issues(conn, model)
    if common_issues:
        context += "\nCommon Issues for this Model:\n"
        for issue in common_issues:
            context += f"- Problem: {issue[0][:100]}\n"
            context += f"  Solution: {issue[1][:100]}\n"
    
    conn.close()
    return context

def build_context_with_embeddings(model=None, serial=None, user_query=None):
    """Build context using vector embeddings for semantic search"""
    conn = connect_database()
    if conn is None:
        return "Error connecting to database."
    
    # Get basic machine information
    machine_details = ""
    if model or serial:
        machine_history = get_machine_history(conn, model, serial)
        if machine_history:
            machine_info = machine_history[0]  # First row has the machine info
            machine_details = f"Machine Details:\n"
            machine_details += f"Model: {machine_info[1]}\n"
            machine_details += f"Serial: {machine_info[0]}\n"
            machine_details += f"Installation Date: {machine_info[2]}\n\n"
            
            # Save model and serial for filtering
            if not model and machine_info[1]:
                model = machine_info[1]
            if not serial and machine_info[0]:
                serial = machine_info[0]
    
    # Build vector search query
    context = "Machine Service History Analysis:\n\n"
    context += machine_details
    
    # Perform vector search if we have a query
    if user_query:
        # Prepare filter
        filter_dict = {}
        if model:
            filter_dict["model"] = {"$like": f"%{model}%"}
        if serial:
            filter_dict["serial"] = serial
            
        # Query vector database for semantically similar reports
        results = service_reports_collection.query(
            query_texts=[user_query],
            n_results=5,
            where=filter_dict if filter_dict else None
        )
        
        if results and results['ids'] and results['ids'][0]:
            context += "Semantically Relevant Service History:\n"
            for i, report_id in enumerate(results['ids'][0]):
                # Get full report details from SQL database
                report_data = get_service_report_by_id(conn, report_id)
                if report_data:
                    context += f"\nService Report {report_id} (Relevance Score: {results['distances'][0][i]:.2f}):\n"
                    context += f"Model: {report_data[2]}\n"
                    context += f"Date: {report_data[1]}\n"
                    if report_data[4]:  # WorkRequired
                        context += f"Issue: {report_data[4]}\n"
                    if report_data[5]:  # ServicePerformed
                        context += f"Solution: {report_data[5]}\n"
                    if report_data[6]:  # VerificationTest
                        context += f"Verification: {report_data[6]}\n"
                    
                    # Get parts used
                    parts = get_related_parts(conn, report_id)
                    if parts:
                        context += "Parts Used: " + ", ".join([f"{p[0]} ({p[1]})" for p in parts[:3]]) + "\n"
    
    # If we have a model but no semantic results yet, add common issues
    if model and not user_query:
        common_issues = get_common_issues(conn, model)
        if common_issues:
            context += "\nCommon Issues for this Model:\n"
            for issue in common_issues:
                context += f"- Problem: {issue[0][:100]}\n"
                context += f"  Solution: {issue[1][:100]}\n"
    
    conn.close()
    return context

def get_openai_response(messages):
    try:
        # Estimate token count
        total_chars = sum(len(m["content"]) for m in messages)
        estimated_tokens = total_chars / 4
        
        if estimated_tokens > 15000:
            # Truncate the system message content if too long
            system_content = messages[0]["content"]
            messages[0]["content"] = system_content[:int(len(system_content) * 0.5)]
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=500,
            n=1,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Error: {str(e)}"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    model = data.get("model", "")
    serial = data.get("serial", "")
    user_query = data.get("query", "")
    conversation = data.get("conversation", [])
    
    if not model and not serial:
        return jsonify({"response": "Error: Please provide either a machine model or serial number."})
    
    # Ensure the vector database is indexed
    if service_reports_collection.count() == 0:
        index_service_reports()
    
    # Build context from service reports using embeddings
    context = build_context_with_embeddings(model, serial, user_query)
    if context.startswith("Error") or context.startswith("No service"):
        return jsonify({"response": context})
    
    # Create a comprehensive system prompt
    system_prompt = """You are a specialized Haas CNC service assistant with deep knowledge of CNC machinery maintenance and repair. 
Your responses should:
1. Analyze the service history to identify patterns and recurring issues
2. Consider the machine's age and maintenance history when providing recommendations
3. Reference specific parts and procedures from past successful repairs
4. Provide step-by-step troubleshooting guidance
5. Suggest preventive maintenance based on historical issues

Use the following service history and related information to provide detailed, actionable recommendations:

{0}""".format(context)
    
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(conversation)
    
    response_text = get_openai_response(messages)
    return jsonify({"response": response_text})

if __name__ == "__main__":
    # Ensure vector database is indexed on startup
    if service_reports_collection.count() == 0:
        index_service_reports()
    app.run(debug=True)