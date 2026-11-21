import 'vite/modulepreload-polyfill';

import './js/style.js';
import './js/ui.js';
import './js/bootstrap.js';
import './js/select.js';
import './js/datepicker.js';
import './js/autosize.js';
import './js/charts.js';
import './js/_utils.js';
// last: this starts Alpine, and components read the globals set up above on first init
import './js/htmx.js';
