import htmx from 'htmx.org';
import 'htmx.org/dist/ext/hx-download.js';
import 'htmx.org/dist/ext/hx-alpine-compat.js';
import 'basecoat-css/all';

window.htmx = htmx;

// Re-initialize Basecoat UI interactive components inside HTMX-swapped fragments.
document.addEventListener('htmx:after:swap', () => {
    window.basecoat?.initAll();
});
