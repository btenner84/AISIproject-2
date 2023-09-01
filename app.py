from flask import Flask, request, render_template, redirect, url_for, g
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import sqlite3
import ast
import os
from dotenv import load_dotenv
load_dotenv() 
import time
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import openai

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['DEBUG'] = False
app.config['TESTING'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


DATABASE = 'database.db'
openai.api_key = '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'
sendgrid_api_key = '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'

class User(UserMixin):
    def __init__(self, id):
        self.id = id

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = dict_factory
    return db

def create_users_table():
    db = get_db()
    db.execute(
        "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, password TEXT, phone TEXT, email TEXT)"
    )
    db.commit()
with app.app_context():
    create_users_table()

def drop_users_table():
    db = get_db()
    db.execute("DROP TABLE IF EXISTS users")
    db.commit()


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        # Fetch the user from the database
        cur = get_db().cursor()
        cur.execute('SELECT * FROM users WHERE username = ?', (username,))
        user = cur.fetchone()
        # Validate the user
        if user is not None and user['password'] == password:  # Replace with password hash check in production
            remember = 'remember' in request.form
            login_user(User(user['id']), remember=remember)
            return redirect(url_for('research'))
        else:
            return 'Invalid credentials'
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        print(request.form)
        username = request.form['username']
        password = request.form['password']
        phone = request.form['phone']
        email = request.form['email']
        cur = get_db().cursor()
        cur.execute('INSERT INTO users (username, password, phone, email) VALUES (?, ?, ?, ?)', (username, password, phone, email))
        get_db().commit()
        return redirect(url_for('login'))
    return render_template('signup.html')



@login_manager.user_loader
def load_user(user_id):
    return User(user_id)


@app.route('/', methods=['GET'])
def home():
    return render_template('home.html', logged_in=current_user.is_authenticated)


def create_responses_table():
    db = get_db()
    db.execute(
        "CREATE TABLE IF NOT EXISTS responses (id INTEGER PRIMARY KEY, report_id INTEGER, source_email TEXT, response_text TEXT)"
    )
    db.commit()

def drop_users_table():
    db = get_db()
    db.execute("DROP TABLE IF EXISTS users")
    db.commit()
with app.app_context():
    drop_users_table()
    create_users_table()
    create_responses_table() 




@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


@app.route('/research', methods=['GET', 'POST'])
@login_required
def research():
    if request.method == 'POST':
        # Collect dynamic questions
        questions = {}
        sources = {}
        for key, value in request.form.items():
            if key.startswith('question_'):
                questions[key] = value
            elif key.startswith('source_'):
                parts = key.split('_')
                source_id = parts[1]
                if len(parts) >= 3:
                    source_field = parts[2]
                    if source_id not in sources:
                        sources[source_id] = {}
                    sources[source_id][source_field] = value

        report = {
            'topic': request.form['topic'],
            'date': request.form['date'],
            'companies_involved': request.form['companies_involved'],
            'context': request.form['context'],
            'source_base': request.form['source_base'],
            'sources': sources,  # Now this is a dictionary containing all dynamic sources
            'questions': questions  # Now this is a dictionary containing all dynamic questions
        }

        # Store the report in the database
        cur = get_db().cursor()
        cur.execute('INSERT INTO reports (topic, date, companies_involved, context, source_base, sources, questions) VALUES (?, ?, ?, ?, ?, ?, ?)',
                    (report['topic'], report['date'], report['companies_involved'], report['context'], report['source_base'], str(report['sources']), str(report['questions'])))
        get_db().commit()

        return redirect(url_for('research_reports'))
    return render_template('index.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route('/research_reports', methods=['GET'])
def research_reports():
    cur = get_db().cursor()
    cur.execute('SELECT * FROM reports')
    reports = cur.fetchall()
    return render_template('research_reports.html', reports=reports)

@app.route('/report/<int:report_id>', methods=['GET'])
def report_details(report_id):
    cur = get_db().cursor()
    cur.execute('SELECT * FROM reports WHERE id = ?', (report_id,))
    report = cur.fetchone()
    if report is not None:
        # Convert the questions and sources back to a dictionary
        questions = ast.literal_eval(report['questions'])
        sources = ast.literal_eval(report['sources'])
        return render_template('report_details.html', report=report, questions=questions, sources=sources)
    else:
        return "Report not found", 404

@app.route('/delete_report/<int:report_id>', methods=['POST'])
def delete_report(report_id):
    cur = get_db().cursor()
    cur.execute('DELETE FROM reports WHERE id = ?', (report_id,))
    get_db().commit()
    return redirect(url_for('research_reports'))
@app.route('/report/<int:report_id>/sources', methods=['GET'])
def report_sources(report_id):
    cur = get_db().cursor()
    cur.execute('SELECT sources FROM reports WHERE id = ?', (report_id,))
    sources = cur.fetchone()
    if sources is not None:
        # Convert the sources back to a dictionary
        sources = ast.literal_eval(sources['sources'])
        return render_template('report_sources.html', sources=sources)
    else:
        return "Report not found", 404




@app.route('/initiate_interview/<int:report_id>', methods=['GET'])
def initiate_interview(report_id):
    cur = get_db().cursor()
    cur.execute('SELECT * FROM reports WHERE id = ?', (report_id,))
    report = cur.fetchone()
    sources = ast.literal_eval(report['sources'])
    for source in sources.values():
        # Generate email content with GPT-3 for each source
        email_content = generate_email_content_with_llm(report, source)
        # If the email content is empty, use a fallback message
        if not email_content.strip():
            email_content = "Apologies, but we were unable to generate a custom message at this time."
        # Send email to each source with SendGrid
        send_email_to_sources(source, email_content)
    return "Initial emails have been sent!"
def generate_email_content_with_llm(report, source):
    # Use the OpenAI API to generate the email content
    email_prompt = f"Dear {source['name']},\n\nI hope this message finds you well. My name is Benjamin Tenner and I am a representative of Alpha3I, a marketplace intelligence company. We specialize in providing comprehensive market analysis and insights for various industries.\n\nWe are currently working on a report focusing on {report['topic']}. Given your extensive experience and expertise in {source['title']}, we believe your insights could be invaluable in understanding the current trends, challenges, and opportunities in this field.\n\nWe would greatly appreciate if you could spare some time to answer a few questions related to the subject. Your input will be instrumental in shaping our report and helping us provide a more accurate and detailed analysis.\n\nPlease let us know a convenient time for you, and we can arrange a call or a meeting as per your preference.\n\nThank you for considering our request. We look forward to your positive response.\n\nBest regards,\n\nBenjamin Tenner\nHead of Research\nbentenner84@gmail.com\n5164623146"
    email_content = openai.ChatCompletion.create(
        model="gpt-4-0613",  # Update the model version
        messages=[
            {"role": "system", "content": f"You are a representative of Alpha3I writing an email to {source['name']}, who is an expert in {source['title']}. The email is about a report on {report['topic']}. Remember to always start email saying Dear {source['name']} and remember that you are Benjamin Tenne, Head of Research, your email btenner@alpha3I.info and your phone number is 5164623146 . Also remember to be very casual and human like and concise"},
            {"role": "user", "content": email_prompt}
        ],
    )
    if 'message' in email_content.choices[0]:
        return email_content.choices[0].message['content']
    else:
        return "Apologies, but we were unable to generate a custom message at this time."
def send_email_to_sources(source, email_content):
    # Use the SendGrid API to send the email
    message = Mail(
        from_email='btenner@alpha3i.info',
        to_emails=source['email'],
        subject='Interview Request',
        plain_text_content=email_content)

    try:
        sg = SendGridAPIClient(sendgrid_api_key)
        response = sg.send(message)
        print(f"Email sent to {source['email']}. Status code: {response.status_code}")
    except Exception as e:
        print(f"Failed to send email to {source['email']}. Error: {str(e)}")
        if hasattr(e, 'body'):
            print(f"Error details: {e.body}")
if __name__ == "__main__":
    app.run(debug=True)
def get_source_from_email(email):
    # Fetch all reports from the database
    cur = get_db().cursor()
    cur.execute('SELECT * FROM reports')
    reports = cur.fetchall()
    print(reports)  # Add this line
    # Iterate over each report
    for report in reports:
        # Convert the sources back to a dictionary
        sources = ast.literal_eval(report['sources'])
        # Iterate over each source in the report
        for source in sources.values():
            # If the source's email matches the given email, return the source and the report
            if source['email'] == email:
                return source, report
    # If no matching source is found, return None
    return None, None


@app.route('/handle_email_response', methods=['POST'])
def handle_email_response():
    print("Received a POST request at /handle_email_response")
    # Parse the incoming JSON
    data = request.get_json()
    # Extract the email address of the sender and the text of the email
    from_email = data['from']
    email_text = data['text']
    print(f"Received email from {from_email} with text: {email_text}")

    # Extract the report_id from the report
    source, report = get_source_from_email(from_email)
    report_id = report['id'] if report else None

    # Insert the response into the responses table
    cur = get_db().cursor()
    cur.execute('INSERT INTO responses (report_id, source_email, response_text) VALUES (?, ?, ?)', (report_id, from_email, email_text))
    get_db().commit()

    # Check if the email text contains the word "agree"
    if "agree" in email_text.lower():
        print("The source has agreed to answer questions.")
        # If the source has agreed to answer questions, generate and send the follow-up email
        if report is not None:
            print(f"Found report for source: {report}")
            if source is not None:
                print(f"Found source details: {source}")
                print("Starting to generate the follow-up email content.")
                follow_up_email_content = generate_follow_up_email_content_with_gpt3(report, source)
                print("Follow-up email content generated. Starting to send the email.")
                send_email_to_sources(source, follow_up_email_content)
                print("Follow-up email sent.")
            else:
                print("No source details found.")
        else:
            print("No report found for source.")
    else:
        print("The source has not agreed to answer questions.")
    return '', 200

def generate_follow_up_email_content_with_gpt3(report, source):
    # Use the OpenAI API to generate the follow-up email content
    email_prompt = f"Dear {source['name']},\n\nThank you for agreeing to answer our questions about {report['topic']}. Here are our questions:\n\n{report['questions']}\n\nWe look forward to your responses.\n\nBest regards,\n\nBenjamin Tenner\nHead of Research\nbentenner84@gmail.com\n5264623146"
    email_content = openai.ChatCompletion.create(
        model="gpt-4-0613",  # Update the model version
        messages=[
            {"role": "system", "content": "use the email promt to help generate a follow-up email to a source for the specific report. Remember that the info for who we are and who we are reaching out can be found in the parameters source and report. do not include a subject:__ in the email"},
            {"role": "user", "content": email_prompt}
        ],
    )
    if 'message' in email_content.choices[0]:
        return email_content.choices[0].message['content']
    else:
        return "Apologies, but we were unable to generate a custom message at this time."

@app.route('/report_calculations/<int:report_id>', methods=['GET', 'POST'])
def report_calculations(report_id):
    cur = get_db().cursor()
    cur.execute('SELECT * FROM reports WHERE id = ?', (report_id,))
    report = cur.fetchone()
    if report is not None:
        # Convert the questions back to a dictionary
        questions = ast.literal_eval(report['questions'])
        # Create a matrix for the report calculations
        num_rows = int(request.form.get('num_rows', 1))
        matrix = [['' for _ in range(len(questions) + 3)] for _ in range(num_rows)]
        return render_template('report_calculations.html', matrix=matrix, questions=questions)
    else:
        return "Report not found", 404



if __name__ == "__main__":
    app.run(debug=True)