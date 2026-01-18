# app.py - HBV Sponsor Outreach Agent (Updated for AutoGen 0.7.x / autogen-agentchat - Jan 2026)

import os
import streamlit as st
import logging
import time
import sqlite3
import pandas as pd
from datetime import datetime
from functools import wraps
from duckduckgo_search import DDGS
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ====================== CONFIG & LOGGING ======================
logging.basicConfig(
    filename='hbv_outreach.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filemode='a'
)

def log_action(action: str, details: str = ""):
    logging.info(f"{action} | {details}")
    print(f"LOG: {action} | {details}")

# Rate limiting for emails (safe for Gmail)
def rate_limit(seconds_between_emails: int = 5):
    last_called = 0
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            nonlocal last_called
            elapsed = time.time() - last_called
            if elapsed < seconds_between_emails:
                time.sleep(seconds_between_emails - elapsed)
            result = func(*args, **kwargs)
            last_called = time.time()
            return result
        return wrapper
    return decorator

# ====================== DATABASE ======================
DB_FILE = "sponsors.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS sponsors (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 name TEXT, email TEXT UNIQUE, description TEXT, source TEXT,
                 priority INTEGER DEFAULT 0, added_date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS outreach (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 sponsor_id INTEGER, sent_date TEXT, status TEXT, message TEXT,
                 FOREIGN KEY(sponsor_id) REFERENCES sponsors(id))''')
    conn.commit()
    conn.close()
    log_action("Database initialized")

init_db()

# ====================== EMAIL TEMPLATE ======================
HTML_TEMPLATE = """\
<html>
  <body style="font-family: Arial, sans-serif; line-height: 1.7; color: #333;">
    <h2 style="color: #2c3e50;">Request for Support – Chronic Hepatitis B Treatment</h2>
    <p>Dear {recipient_name_or_team},</p>
    <p>I am <strong>Genesis Koodanga</strong>, a 25-year-old Christian secondary school teacher from Zing LGA, Taraba State, Nigeria. 
    I hold a degree in Linguistics from Taraba State University Jalingo and completed my NYSC in 2024.</p>
    
    <p>I have been diagnosed with <strong>chronic Hepatitis B</strong> and I am reaching out with hope and faith for any possible support with:</p>
    <ul>
      <li>Medical tests and monitoring</li>
      <li>Antiviral treatment/medication</li>
      <li>Travel expenses for specialist care</li>
      <li>Liver transplant evaluation (if required in future)</li>
    </ul>
    
    <p>I remain committed to my teaching work and writing while believing God for complete healing. 
    Any assistance or guidance your organization can offer would be a tremendous blessing.</p>
    
    <p>Thank you sincerely for your time and kind consideration.</p>
    
    <p>With gratitude and hope,<br>
    <strong>Genesis Koodanga</strong><br>
    Secondary School Teacher & Writer<br>
    Taraba State, Nigeria<br>
    Phone: [Your Phone] | Email: [Your Email]</p>
  </body>
</html>
"""

# ====================== TOOLS ======================
def web_search(query: str, max_results: int = 15) -> str:
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        if not results:
            return "No results found."
        formatted = "\n\n".join([
            f"Title: {r['title']}\nLink: {r['href']}\nSnippet: {r['body']}"
            for r in results
        ])
        return formatted
    except Exception as e:
        return f"Search error: {str(e)}"

@rate_limit(seconds_between_emails=5)
def send_email(to_email: str, subject: str, body_html: str, from_email: str,
               smtp_server: str, smtp_port: int, username: str, password: str) -> str:
    try:
        msg = MIMEMultipart("alternative")
        msg['From'] = from_email
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body_html, 'html'))

        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(username, password)
        server.sendmail(from_email, to_email, msg.as_string())
        server.quit()
        
        log_action("EMAIL SENT", f"To: {to_email}")
        return f"✅ Sent to {to_email}"
    except Exception as e:
        error_msg = f"Failed to {to_email}: {str(e)}"
        log_action("EMAIL FAILED", error_msg)
        return error_msg

# Simple priority scoring
def calculate_priority(description: str) -> int:
    score = 0
    keywords_high = ["hepatitis b", "hbv", "liver", "transplant", "nigeria", "africa", "grant", "sponsor"]
    keywords_medium = ["medical", "health", "christian", "charity", "donation", "ngo"]
    desc = description.lower()
    for kw in keywords_high:
        if kw in desc: score += 20
    for kw in keywords_medium:
        if kw in desc: score += 8
    return min(score, 100)

# ====================== AUTOGEN SETUP (2026 version - autogen-agentchat) ======================
from autogen_agentchat.agents import AssistantAgent, UserProxyAgent
from autogen_agentchat.teams import GroupChat, GroupChatManager
from autogen_agentchat import register_function

llm_config = {
    "config_list": [{"model": "gpt-4o-mini", "api_key": os.getenv("OPENAI_API_KEY")}],
    "temperature": 0.7,
}

user_proxy = UserProxyAgent(
    name="UserProxy",
    human_input_mode="NEVER",
    code_execution_config={"work_dir": "code", "use_docker": False},
    max_consecutive_auto_reply=6,
)

researcher = AssistantAgent(
    name="Researcher",
    llm_config=llm_config,
    system_message="Search the web deeply for organizations, churches, NGOs, individuals, or grants that help with Hepatitis B treatment, tests, travel, or transplants — especially in Nigeria/Africa or faith-based groups."
)

analyzer = AssistantAgent(
    name="Analyzer",
    llm_config=llm_config,
    system_message="""Extract sponsor name, email (if any), description, and website.
    Calculate priority score. Save high-priority contacts to the SQLite database.
    NEVER send email without final human approval."""
)

outreach_writer = AssistantAgent(
    name="OutreachWriter",
    llm_config=llm_config,
    system_message="Write a short, warm, professional HTML email using the template. Personalize slightly when possible."
)

email_sender = AssistantAgent(
    name="EmailSender",
    llm_config=llm_config,
    system_message="You may ONLY send emails when the human explicitly clicks 'Send All Approved Emails' in the app."
)

register_function(web_search, caller=researcher, executor=user_proxy, name="web_search")
register_function(send_email, caller=email_sender, executor=user_proxy, name="send_email")

groupchat = GroupChat(
    agents=[user_proxy, researcher, analyzer, outreach_writer, email_sender],
    messages=[],
    max_round=15,
)

manager = GroupChatManager(groupchat=groupchat, llm_config=llm_config)

# ====================== STREAMLIT APP ======================
st.set_page_config(page_title="Genesis HBV Sponsor Agent", layout="wide")
st.title("Chronic HBV Sponsor Outreach Agent")
st.markdown("**Research → Database → Outreach (with your final approval)**")

tab1, tab2, tab3, tab4 = st.tabs(["Run Agents", "Database", "Send Emails", "Logs & Export"])

with tab1:
    st.write("### Start New Research")
    query = st.text_area(
        "Research query (edit if needed)",
        value="Hepatitis B treatment sponsors OR grants OR charity OR church help Nigeria OR Africa OR Christian organizations 2025-2026 site:.org OR site:.ng OR site:foundation",
        height=120
    )
    if st.button("Start Full Research Cycle", type="primary"):
        with st.spinner("Agents are researching..."):
            result = user_proxy.initiate_chat(
                manager,
                message=query + "\nFocus on finding real emails and organizations that actually fund HBV patients.",
                summary_method="reflection_with_llm"
            )
            st.success("Research complete!")
            st.write("### Summary")
            st.write(result.summary)

with tab2:
    st.write("### Found Sponsors (auto-saved)")
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM sponsors ORDER BY priority DESC", conn)
    conn.close()
    if not df.empty:
        st.dataframe(df, use_container_width=True)
        csv = df.to_csv(index=False).encode()
        st.download_button("Download as CSV", csv, "hbv_sponsors.csv", "text/csv")
    else:
        st.info("No sponsors in database yet. Run research first.")

with tab3:
    st.write("### Send Outreach Emails (You control this)")
    conn = sqlite3.connect(DB_FILE)
    pending = pd.read_sql_query("""
        SELECT s.id, s.name, s.email, s.priority 
        FROM sponsors s 
        LEFT JOIN outreach o ON s.id = o.sponsor_id 
        WHERE o.id IS NULL AND s.email IS NOT NULL AND s.email LIKE '%@%'
        ORDER BY s.priority DESC
    """, conn)
    conn.close()

    if not pending.empty:
        st.dataframe(pending)
        
        col1, col2 = st.columns([1, 3])
        with col1:
            send_all = st.checkbox("I have reviewed all emails above", value=False)
        with col2:
            if st.button("SEND ALL APPROVED EMAILS NOW", type="secondary", disabled=not send_all):
                with st.spinner("Sending emails..."):
                    from_email = st.session_state.get("from_email", "")
                    password = st.session_state.get("password", "")
                    if not from_email or not password:
                        st.error("Set email credentials in sidebar first")
                    else:
                        results = []
                        for _, row in pending.iterrows():
                            personalized_html = HTML_TEMPLATE.format(recipient_name_or_team=row["name"] or "Team")
                            status = send_email(
                                to_email=row["email"],
                                subject="Request for Support – Chronic Hepatitis B (Nigeria)",
                                body_html=personalized_html,
                                from_email=from_email,
                                smtp_server="smtp.gmail.com",
                                smtp_port=587,
                                username=from_email,
                                password=password
                            )
                            # Log to DB
                            c = sqlite3.connect(DB_FILE)
                            c.execute("INSERT INTO outreach (sponsor_id, sent_date, status, message) VALUES (?, ?, ?, ?)",
                                      (row["id"], datetime.now().strftime("%Y-%m-%d %H:%M"), status, "HTML template"))
                            c.commit()
                            c.close()
                            results.append(f"{row['email']} → {status}")
                        st.success("All emails processed!")
                        for r in results:
                            st.write(r)
    else:
        st.success("No new contacts to email (or all already sent)")

with tab4:
    st.write("### Recent Log")
    try:
        with open("hbv_outreach.log", "r") as f:
            logs = f.read().splitlines()[-50:]
        st.code("\n".join(logs[::-1]))
    except:
        st.write("No log yet")

# ====================== SIDEBAR - CREDENTIALS ======================
with st.sidebar:
    st.header("Email Settings (required for sending)")
    from_email = st.text_input("Your Gmail", value=os.getenv("FROM_EMAIL", ""), type="default")
    password = st.text_input("App Password (Gmail)", type="password", value=os.getenv("EMAIL_PASS", ""))
    if from_email and password:
        st.session_state.from_email = from_email
        st.session_state.password = password
        st.success("Credentials ready")
    else:
        st.info("Use Gmail + App Password (not regular password)")

    st.markdown("---")
    st.markdown("### Quick Guide")
    st.markdown("""
    1. Set Gmail + App Password above  
    2. Run research in Tab 1  
    3. Check found contacts in Tab 2  
    4. Review & send in Tab 3 (only after you approve)
    """)

log_action("App loaded successfully")
