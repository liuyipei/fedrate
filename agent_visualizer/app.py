from flask import Flask, render_template, jsonify
import json
import os
import markdown

app = Flask(__name__)

# Path to the runs directory
RUNS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'runs')
RUN_ID = 'ae30a38d'  # The run ID from the provided files

def load_json_file(filename):
    """Load JSON data from a file."""
    try:
        with open(os.path.join(RUNS_DIR, filename), 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return None

def load_text_file(filename):
    """Load text data from a file."""
    try:
        with open(os.path.join(RUNS_DIR, filename), 'r') as f:
            return f.read()
    except FileNotFoundError:
        return None

@app.route('/')
def index():
    # Load data for all components
    sources_data = load_json_file(f'{RUN_ID}.sources.raw.json')
    macro_notes = load_text_file(f'{RUN_ID}.macro.notes.md')
    factcheck_data = load_json_file(f'{RUN_ID}.factcheck.json')
    brief_content = load_text_file(f'{RUN_ID}.brief.md')
    
    # Convert markdown to HTML
    if macro_notes:
        macro_notes = markdown.markdown(macro_notes, extensions=['tables'])
    
    if factcheck_data:
        factcheck_text = factcheck_data.get('text', '')
        factcheck_flags = factcheck_data.get('flags', [])
        if factcheck_text:
            factcheck_text = markdown.markdown(factcheck_text, extensions=['tables'])
    else:
        factcheck_text = None
        factcheck_flags = []
    
    if brief_content:
        brief_content = markdown.markdown(brief_content, extensions=['tables'])
    
    return render_template('index.html',
                         sources=sources_data,
                         macro_notes=macro_notes,
                         factcheck_text=factcheck_text,
                         factcheck_flags=factcheck_flags,
                         brief_content=brief_content)

@app.route('/api/sources')
def api_sources():
    sources_data = load_json_file(f'{RUN_ID}.sources.raw.json')
    return jsonify(sources_data or [])

@app.route('/api/macro-notes')
def api_macro_notes():
    macro_notes = load_text_file(f'{RUN_ID}.macro.notes.md')
    return jsonify({'content': macro_notes})

@app.route('/api/factcheck')
def api_factcheck():
    factcheck_data = load_json_file(f'{RUN_ID}.factcheck.json')
    return jsonify(factcheck_data or {})

@app.route('/api/brief')
def api_brief():
    brief_content = load_text_file(f'{RUN_ID}.brief.md')
    return jsonify({'content': brief_content})

if __name__ == '__main__':
    app.run(debug=True, port=5001)
