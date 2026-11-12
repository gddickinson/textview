// About page: what TextView is, how to run the desktop and web apps, what the web version leaves out, credits.
import { route, app, isStatic } from './core.js';

route('about', () => {
  app().innerHTML = `<h1>About</h1>
    <p class="lead">TextView is a modular PyQt6 file viewer and lightweight editor by George Dickinson, with an AI agent that
      knows your workspace. Every source file stays under 500 lines; the repo carries a large regression suite.</p>
    <h2>Run the desktop app</h2>
    <pre>git clone https://github.com/gddickinson/textview.git && cd textview
conda env create -f environment.yml && conda activate textview   # or: pip install -r requirements.txt
python main.py                # welcome screen
python main.py path/to/file   # open a file</pre>
    <h2>Run the web app</h2>
    <pre>pip install -r requirements-web.txt
python run_web.py             # http://127.0.0.1:8110</pre>
    <p>The local web app opens your own files with TextView's Python loaders (DOCX, spreadsheets, SQLite, archives,
      NumPy / MATLAB / HDF5 when those libraries are installed) and runs the inspector and security scan in Python.
      ${isStatic() ? 'This static site shows the same pages; the samples were opened by Python when the site was built, and your own files are handled in the browser by JS ports that are tested against the Python code.' : ''}</p>
    <h2>Desktop only</h2>
    <ul><li><b>Chat agent, workspace-RAG answers, inline completions, the agent that writes format handlers and plugins</b>:
      they call an LLM (Anthropic, OpenAI or Ollama) with your key. The web pages never call an external service.</li>
      <li><b>Editing and saving</b>, Save As conversions, PDF page editing, annotations, signing and reconstruction.</li>
      <li><b>LSP</b> (pyright, gopls, …), the <b>Jupyter kernel</b>, terminal, runner, LaTeX compile, 3D mesh view.</li>
      <li>Quarantine, ClamAV and the macOS quarantine-xattr check from the security scanner.</li></ul>
    <p>See <a href="#/docs/overview">the overview</a> and <a href="#/docs/architecture">architecture</a> docs for the full picture.</p>
    <h2>Credits</h2>
    <p>TextView by George Dickinson (<a href="https://github.com/gddickinson/textview">gddickinson/textview</a>), MIT licence.
      Built on PyQt6, Pygments, Python-Markdown, pypdf, python-docx, mammoth, Pillow, openpyxl and the other libraries in
      requirements.txt.</p>`;
});
