#!/usr/bin/env python3
"""
Specialized GPT Agent for Haas CNC Service Assistance

This script implements a specialized GPT clone that:
- Connects to the masterData.sqlite3 database.
- Retrieves service reports and related parts information based on a specified machine model.
- Uses OpenAI's GPT engine to generate troubleshooting recommendations using both the database context and the user's symptoms.

Requirement
- masterData.sqlite3 in the same directory (or update the db_path accordingly).
- Python packages: sqlite3 (builtin), openai (install via `pip install openai`).
- OPENAI_API_KEY environment variable set with your OpenAI API key.
"""

import os
import sqlite3
import sys
import openai

class SpecializedGPTAgent:
    def __init__(self, db_path='masterData.sqlite3'):
        self.db_path = db_path
        self.conn = self.connect_database()
        self.system_prompt = (
            "You are a specialized Haas CNC service assistant, an expert in troubleshooting, repairing, and maintaining Haas CNC machinery. "
            "Use the provided service report details and parts information to offer precise and actionable recommendations based on the user's symptoms."
        )
        # Ensure OpenAI API key is set
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            print("Error: OPENAI_API_KEY environment variable is not set.")
            sys.exit(1)
        self.client = openai.OpenAI(api_key=openai_api_key)

    def connect_database(self):
        """
        Connect to the SQLite database.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            return conn
        except Exception as e:
            print("Error connecting to database:", e)
            sys.exit(1)

    def get_service_reports(self, model):
        """
        Retrieve service reports from the ServiceReports table that match the specified machine model.
        """
        cursor = self.conn.cursor()
        query = """
        SELECT ServiceReport_id, WorkRequired, ServicePerformed, VerificationTest, Model
        FROM ServiceReports
        WHERE Model LIKE ?
        """
        cursor.execute(query, (f"%{model}%",))
        rows = cursor.fetchall()
        reports = []
        for row in rows:
            reports.append({
                "ServiceReport_id": row[0],
                "WorkRequired": row[1],
                "ServicePerformed": row[2],
                "VerificationTest": row[3],
                "Model": row[4]
            })
        return reports

    def get_service_report_parts(self, service_report_id):
        """
        Retrieve parts information from the ServiceReportParts table for a given service report.
        """
        cursor = self.conn.cursor()
        query = """
        SELECT PartNumber, Description
        FROM ServiceReportParts
        WHERE ServiceReport_id = ?
        """
        cursor.execute(query, (service_report_id,))
        rows = cursor.fetchall()
        parts = []
        for row in rows:
            parts.append({
                "PartNumber": row[0],
                "Description": row[1]
            })
        return parts

    def build_context(self, model):
        """
        Build a context string containing service report and parts details for the given machine model.
        """
        reports = self.get_service_reports(model)
        if not reports:
            return "No service reports found for the specified model."
        context = "Service Report Details:\n"
        for report in reports:
            parts = self.get_service_report_parts(report["ServiceReport_id"])
            report["Parts"] = parts
            context += f"Service Report ID: {report['ServiceReport_id']}\n"
            context += f"Model: {report.get('Model', 'N/A')}\n"
            context += "Work Required: " + (report.get("WorkRequired") or "N/A") + "\n"
            context += "Service Performed: " + (report.get("ServicePerformed") or "N/A") + "\n"
            context += "Verification Test: " + (report.get("VerificationTest") or "N/A") + "\n"
            if parts:
                context += "Parts Used:\n"
                for part in parts:
                    context += f" - Part Number: {part['PartNumber']}, Description: {part['Description']}\n"
            context += "\n"
        return context

    def generate_response(self, model, symptoms):
        """
        Generate a troubleshooting response from OpenAI's GPT engine using the context from the database and user input.
        """
        context = self.build_context(model)
        user_prompt = (
            f"Machine Model: {model}\n"
            f"User Reported Symptoms: {symptoms}\n\n"
            "Please analyze the above information and provide a detailed troubleshooting summary, including likely issues, recommended solutions, and any relevant parts information."
        )
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": context + "\n" + user_prompt}
        ]
        try:
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",  # Updated model name
                messages=messages,
                temperature=1
            )
            return response.choices[0].message.content
        except Exception as e:
            return "Error generating response: " + str(e)

def main():
    print("Specialized GPT Agent for Haas CNC Service Assistance")
    model = input("Enter the machine model (e.g., VF-4): ").strip()
    symptoms = input("Enter the symptoms or issues observed: ").strip()
    
    agent = SpecializedGPTAgent()
    response = agent.generate_response(model, symptoms)
    
    print("\n--- GPT Analysis & Recommendations ---\n")
    print(response)

if __name__ == "__main__":
    main()
