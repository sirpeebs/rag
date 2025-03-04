import os
import sqlite3
import openai
from flask import Flask, render_template, request, jsonify
from datetime import datetime

# Initialize the OpenAI client with your API key
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
db_path = os.path.join(os.path.dirname(__file__), '..', 'masterData.sqlite3')

def connect_database():
    try:
        conn = sqlite3.connect(db_path)
        return conn
    except Exception as e:
        print("Error connecting to database:", e)
        return None

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

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    model = data.get("model", "")
    serial = data.get("serial", "")
    conversation = data.get("conversation", [])
    
    if not model and not serial:
        return jsonify({"response": "Error: Please provide either a machine model or serial number."})
    
    # Build context from service reports
    context = build_context(model, serial)
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

{context}"""
    
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(conversation)
    
    response_text = get_openai_response(messages)
    return jsonify({"response": response_text})

if __name__ == "__main__":
    app.run(debug=True)