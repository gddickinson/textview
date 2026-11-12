// Entry point: registers lazily loaded pages, sets the footer mode text and starts the router.
import { start, lazy, route, app, isStatic, $ } from './core.js';

const PAGES = { 'home.js': ['home'], 'viewer.js': ['view'], 'inspect.js': ['inspect'], 'formats.js': ['formats'],
  'search.js': ['search'], 'docs.js': ['docs'], 'about.js': ['about'] };
lazy(Object.fromEntries(Object.entries(PAGES).flatMap(([file, names]) => names.map(n => [n, () => import('./' + file)]))));
route('notfound', () => { app().innerHTML = '<h1>Not found</h1><p><a href="#/">Back to the start</a></p>'; });

$('#mode').textContent = isStatic()
  ? 'static site: sample files pre-rendered by the Python app; your own files are read in your browser (JS ports)'
  : 'local app: files are opened by TextView\'s Python loaders';
start();
