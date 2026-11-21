// Small UI helpers used from Alpine expressions in the templates.
// Loaded before Alpine starts so the globals exist on first init.
import Alpine from 'alpinejs';

// Slide a segmented control's pill under its pressed button.
window.tlSeg = function tlSeg(el) {
    const active = el.querySelector('[aria-pressed="true"]');
    if (!active) return;
    el.style.setProperty('--seg-x', `${active.offsetLeft - 3}px`);
    el.style.setProperty('--seg-w', `${active.offsetWidth}px`);
    // first placement snaps; later ones glide
    if (el.dataset.ready !== 'true') requestAnimationFrame(() => { el.dataset.ready = 'true'; });
    // re-measure when button widths change (web font arriving, sidebar resizing the layout)
    if (!el._segObserved) {
        el._segObserved = true;
        new ResizeObserver(() => tlSeg(el)).observe(el);
    }
};

// "3d 4h", "2h 05m", "12m", "<1m"
window.tlElapsed = function tlElapsed(iso) {
    const mins = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 60000));
    if (mins < 1) return '<1m';
    const d = Math.floor(mins / 1440);
    const h = Math.floor((mins % 1440) / 60);
    const m = mins % 60;
    if (d) return `${d}d ${h}h`;
    if (h) return `${h}h ${String(m).padStart(2, '0')}m`;
    return `${m}m`;
};

// Loose clock input: "9" "930" "9:30" "21h" "9pm" -> "09:00" "09:30" "09:30" "21:00" "21:00".
// Blank stays blank (all day); anything unreadable is returned as typed.
window.tlClock = function tlClock(raw) {
    const s = (raw || '').trim().toLowerCase();
    if (!s) return '';
    const m = s.match(/^(\d{1,2})(?:[:h.]?(\d{2}))?\s*(am|pm|a|p|h)?$/);
    if (!m) return raw;
    let h = Number(m[1]);
    const min = Number(m[2] || 0);
    if (m[3]?.startsWith('p') && h < 12) h += 12;
    if (m[3]?.startsWith('a') && h === 12) h = 0;
    if (h > 23 || min > 59) return raw;
    return `${String(h).padStart(2, '0')}:${String(min).padStart(2, '0')}`;
};

// ---------------------------------------------------------------------------
// Token suggestions for the search box and Quick log. Mixed into a component's
// data with `...tlSuggest('search' | 'quick', 'refName')`; reads endpoints and
// labels from the #suggest-config JSON on the page.
// ---------------------------------------------------------------------------
const suggestConfig = () => JSON.parse(document.getElementById('suggest-config')?.textContent || '{}');
const getJson = async (url) => {
    const res = await fetch(url);
    return res.ok ? res.json() : null;
};

// the whitespace-delimited word around the caret, and what's typed of it so far
const tokenAt = (el) => {
    const v = el.value;
    const caret = el.selectionStart ?? v.length;
    let start = caret;
    while (start > 0 && !/\s/.test(v[start - 1])) start--;
    let end = caret;
    while (end < v.length && !/\s/.test(v[end])) end++;
    return {start, end, typed: v.slice(start, caret)};
};

// Common moments for a bare "@", as canonical @-text the server reads back exactly.
// A day without a time is logged at the current time of day.
function datePresets(labels) {
    const lang = document.documentElement.lang || undefined;
    const hm = new Intl.DateTimeFormat(lang, {hour: '2-digit', minute: '2-digit'});
    const day = new Intl.DateTimeFormat(lang, {weekday: 'short', day: 'numeric', month: 'short'});
    const pad = (n) => String(n).padStart(2, '0');
    const at = (d) => `${isoDay(d.getTime())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
    const now = new Date();
    const ago = (mins) => new Date(now.getTime() - mins * 60000);
    const todayAt = (h) => { const d = new Date(now); d.setHours(h, 0, 0, 0); return d; };
    const yesterdayAt = (h) => { const d = todayAt(h); d.setDate(d.getDate() - 1); return d; };
    const daysAgo = (n) => addDays(startOfDay(now.getTime()), -n);

    // a bare date is an all-day event, so "today" and "now" are different things
    const allDay = (d) => `${day.format(d)}, ${labels.allDay}`;
    const out = [
        {label: labels.now, d: now},
        {label: labels.min30, d: ago(30)},
        {label: labels.hour1, d: ago(60)},
        {label: labels.hour3, d: ago(180)},
    ].map(({label, d}) => ({label, hint: hm.format(d), value: at(d)}));
    if (now.getHours() >= 10) out.push({label: labels.morning, hint: hm.format(todayAt(8)), value: at(todayAt(8))});
    out.push(
        {label: labels.today, hint: allDay(daysAgo(0)), value: isoDay(daysAgo(0))},
        {label: labels.yesterday, hint: allDay(daysAgo(1)), value: isoDay(daysAgo(1))},
        {label: labels.yesterdayEvening, hint: `${day.format(daysAgo(1))}, ${hm.format(yesterdayAt(20))}`, value: at(yesterdayAt(20))},
        {label: labels.days2, hint: allDay(daysAgo(2)), value: isoDay(daysAgo(2))},
        {label: labels.week1, hint: allDay(daysAgo(7)), value: isoDay(daysAgo(7))},
    );
    return out;
}

async function suggestionsFor(el, mode) {
    const cfg = suggestConfig();
    const tok = tokenAt(el);
    const t = tok.typed;
    const q = (s) => encodeURIComponent(s);

    const tag = t.match(mode === 'search' ? /^(-?)#([\w-]*)$/ : /^()#([\w-]*)$/);
    if (tag) {
        const term = tag[2].toLowerCase();
        const present = new Set([...el.value.matchAll(/#([\w-]+)/g)].map((m) => m[1].toLowerCase()));
        present.delete(term);
        const tags = ((await getJson(`${cfg.tags}?q=${q(term)}`))?.tags || [])
            .filter((x) => !present.has(x.slug)).slice(0, 6);
        // nothing left to offer once the whole tag is typed
        if (tags.length === 1 && tags[0].slug === term) return {tok, items: []};
        return {tok, items: tags.map((x) => ({
            label: `${tag[1]}#${x.name}`, color: x.color, meta: x.event_count,
            insert: `${tag[1]}#${x.slug} `, enter: true,
        }))};
    }
    if (mode === 'quick') {
        // @date: shortcuts when empty, otherwise every reading of what's typed
        if (t.startsWith('@')) {
            const rest = t.slice(1);
            // nothing typed yet, or a word ("yes"): common moments, filtered by name
            if (!rest || /^[a-z]/i.test(rest)) {
                const presets = datePresets(cfg.presets)
                    .filter((p) => !rest || p.label.toLowerCase().includes(rest.toLowerCase()))
                    .map((p) => ({...p, insert: `@${p.value} `, date: true, enter: true}));
                return {tok, items: [...presets, {label: '@', hint: cfg.dateHint, insert: t, inert: true}]};
            }
            const opts = (await getJson(`${cfg.dates}?q=${q(rest)}`))?.options || [];
            if (opts.length === 1 && opts[0].value === rest) return {tok, items: []};
            return {tok, items: opts.map((o) => ({
                label: o.label, hint: opts.length > 1 ? cfg.ambiguousHint : '',
                insert: `@${o.value} `, date: true,
                // one clear reading: Enter still logs the event, Tab tidies the date
                enter: opts.length > 1,
            }))};
        }
        // >part of: pick a running event; it becomes a badge, the text is removed
        if (t.startsWith('>')) {
            const events = (await getJson(`${cfg.ongoing}?q=${q(t.slice(1))}`))?.events || [];
            return {tok, items: events.map((ev) => ({
                label: ev.title, hint: ev.since, color: ev.color, parent: ev, insert: '', enter: true,
            }))};
        }
        return {tok, items: []};
    }

    const op = t.match(/^(is|has|last|after|before):(.*)$/i);
    if (op) {
        const [, name, rest] = op;
        const key = name.toLowerCase();
        if (key === 'is' || key === 'last') {
            return {tok, items: cfg[key]
                .filter(([v]) => v.startsWith(rest.toLowerCase()) && v !== rest)
                .map(([v, hint]) => ({label: `${key}:${v}`, hint, insert: `${key}:${v} `, enter: true}))};
        }
        if (key === 'has') {
            const keys = (await getJson(`${cfg.fields}?q=${q(rest)}`))?.keys || [];
            return {tok, items: keys.filter((k) => k !== rest)
                .map((k) => ({label: `has:${k}`, insert: `has:${k} `, enter: true}))};
        }
        // after:/before: take any date style; ambiguous ones list each reading
        if (!rest) return {tok, items: [{label: `${key}:`, hint: cfg.searchDateHint, insert: t, enter: false, inert: true}]};
        const opts = (await getJson(`${cfg.dates}?single=1&q=${q(rest)}`))?.options || [];
        if (opts.length === 1 && opts[0].value === rest) return {tok, items: []};
        return {tok, items: opts.map((o) => ({
            label: o.label, hint: opts.length > 1 ? cfg.ambiguousHint : '',
            insert: `${key}:${o.value} `, enter: true, date: true,
        }))};
    }

    // a bare word: offer operators and field names that start with it
    if (/^[a-z][\w-]*$/i.test(t)) {
        const ops = cfg.ops.filter(([o]) => o.startsWith(t.toLowerCase()))
            .map(([o, hint]) => ({label: o, hint, insert: o, enter: false}));
        const keys = ((await getJson(`${cfg.fields}?q=${q(t)}`))?.keys || [])
            .map((k) => ({label: `${k}:`, hint: cfg.fieldHint, insert: `${k}:`, enter: false}));
        return {tok, items: [...ops, ...keys].slice(0, 7)};
    }
    return {tok, items: []};
}

window.tlSuggest = (mode, refName) => ({
    sugItems: [],
    sugIdx: 0,
    sugSeq: 0,
    sugTok: null,

    async sugRefresh() {
        const el = this.$refs[refName];
        const seq = ++this.sugSeq;
        const {tok, items} = await suggestionsFor(el, mode);
        if (seq !== this.sugSeq || document.activeElement !== el) return;  // stale or left
        this.sugTok = tok;
        this.sugItems = items;
        this.sugIdx = Math.max(0, items.findIndex((i) => !i.inert));
    },

    sugPick(item) {
        if (!item || item.inert) return;
        const el = this.$refs[refName];
        const before = el.value.slice(0, this.sugTok.start) + item.insert;
        let after = el.value.slice(this.sugTok.end);
        if (item.insert.endsWith(' ') && after.startsWith(' ')) after = after.slice(1);
        el.value = before + after;
        el.setSelectionRange(before.length, before.length);
        this.sugItems = [];
        // items that set state rather than text (Quick log's ">part of")
        if (item.parent) this.setParent?.(item.parent);
        // let x-model, live search and the next drill-down level all see the change
        el.dispatchEvent(new Event('input', {bubbles: true}));
    },

    sugKey(e) {
        if (!this.sugItems.length) return;
        const n = this.sugItems.length;
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            e.preventDefault();
            this.sugIdx = (this.sugIdx + (e.key === 'ArrowDown' ? 1 : n - 1)) % n;
        } else if (e.key === 'Tab' || (e.key === 'Enter' && this.sugItems[this.sugIdx]?.enter)) {
            if (this.sugItems[this.sugIdx]?.inert) return;
            e.preventDefault();
            this.sugPick(this.sugItems[this.sugIdx]);
        } else if (e.key === 'Escape') {
            e.stopPropagation();
            this.sugItems = [];
        }
    },

    // closing waits a beat so a click in the list lands first; skip it if focus came
    // back (a badge that blurs the input, then refocuses it and opens a menu)
    sugClose() {
        setTimeout(() => {
            if (document.activeElement !== this.$refs[refName]) this.sugItems = [];
        }, 120);
    },
});

// Read an @date in Quick log text: every reading, so an ambiguous one can be picked.
window.tlInterpretDate = async (raw) => {
    if (!raw) return [];
    const cfg = suggestConfig();
    return (await getJson(`${cfg.dates}?q=${encodeURIComponent(raw)}`))?.options || [];
};

// ---------------------------------------------------------------------------
// Confirm / alert dialog (basecoat .alert-dialog in includes/confirm_dialog.html).
// tlConfirm({title, text, confirmText, cancelText, cancel = true, danger}) -> Promise<bool>
// ---------------------------------------------------------------------------
window.tlConfirm = function tlConfirm({title, text = '', confirmText, cancelText, cancel = true, danger = false} = {}) {
    const dlg = document.getElementById('tl-dialog');
    if (!dlg) return Promise.resolve(window.confirm(title));
    const ok = dlg.querySelector('[data-dialog-confirm]');
    const no = dlg.querySelector('[data-dialog-cancel]');
    dlg.querySelector('#tl-dialog-title').textContent = title || '';
    dlg.querySelector('#tl-dialog-text').textContent = text;
    dlg.querySelector('#tl-dialog-text').hidden = !text;
    ok.textContent = confirmText || dlg.dataset.confirm;
    no.textContent = cancelText || dlg.dataset.cancel;
    no.hidden = !cancel;
    if (danger) ok.dataset.variant = 'destructive'; else delete ok.dataset.variant;

    return new Promise((resolve) => {
        let answered = false;
        const finish = (value) => {
            if (answered) return;
            answered = true;
            ok.onclick = no.onclick = dlg.onclose = null;
            if (dlg.open) dlg.close();
            resolve(value);
        };
        ok.onclick = () => finish(true);
        no.onclick = () => finish(false);
        dlg.onclose = () => finish(false);           // Esc or backdrop
        dlg.showModal();
        // a destructive question starts on the safe answer
        (danger && cancel ? no : ok).focus();
    });
};

document.addEventListener('DOMContentLoaded', () => {
    const dlg = document.getElementById('tl-dialog');
    // Esc answers the dialog only; don't let it also close the drawer or Quick log behind
    dlg?.addEventListener('keydown', (e) => { if (e.key === 'Escape') e.stopPropagation(); });
    // clicking the backdrop (the dialog element itself, outside its panel) cancels
    dlg?.addEventListener('click', (e) => { if (e.target === dlg) dlg.close(); });
});

// hx-confirm="Question?" goes through the dialog. Optional on the same element:
// data-confirm-text (button label), data-confirm-detail (second line), data-confirm-safe
// (not destructive: confirms are treated as destructive by default).
document.addEventListener('htmx:confirm', (e) => {
    const question = e.detail?.ctx?.confirm;
    if (!question) return;
    e.preventDefault();
    const el = e.target;
    window.tlConfirm({
        title: question,
        text: el.dataset.confirmDetail || '',
        confirmText: el.dataset.confirmText,
        danger: !('confirmSafe' in el.dataset),
    }).then((yes) => (yes ? e.detail.issueRequest() : e.detail.dropRequest()));
});

// Highlight the row of an event that was just logged once the feed re-renders.
let freshId = null;
window.addEventListener('eventsChanged', (e) => {
    freshId = e.detail?.id ?? e.detail?.value?.id ?? null;
});
document.addEventListener('htmx:after:settle', () => {
    if (!freshId) return;
    const row = document.querySelector(`[data-event-id="${freshId}"]`);
    freshId = null;
    if (!row) return;
    row.classList.add('is-new');
    row.scrollIntoView({block: 'nearest', behavior: 'smooth'});
    row.addEventListener('animationend', () => row.classList.remove('is-new'), {once: true});
});

// Links marked data-keep-query (Feed <-> Lanes) take the current ?q=&range= along.
// Capture phase, so the href is rewritten before htmx's boost reads it.
['click', 'auxclick'].forEach((type) => document.addEventListener(type, (e) => {
    const link = e.target.closest?.('a[data-keep-query]');
    if (!link) return;
    const base = link.getAttribute('href').split('?')[0];
    link.setAttribute('href', base + location.search);
}, true));

// "/" jumps to search, like most log viewers.
window.addEventListener('keydown', (e) => {
    if (e.key !== '/' || e.ctrlKey || e.metaKey || e.altKey) return;
    if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) return;
    const input = document.querySelector('[data-search-input]');
    if (!input) return;
    e.preventDefault();
    input.focus();
    input.select();
});

// ---------------------------------------------------------------------------
// Lanes: an editing-timeline style view. One column per day, zoom with
// Ctrl/Alt + wheel (anchored at the cursor) or the toolbar, pan by scrolling
// or dragging. Hovering a day lists everything on it; clicking a day on a lane
// opens Quick log pre-filled with that day and the lane's tags.
// ---------------------------------------------------------------------------
const DAY = 86400000;
const MAX_DAY_W = 240;

const startOfDay = (ms) => { const d = new Date(ms); d.setHours(0, 0, 0, 0); return d.getTime(); };
const addDays = (ms, n) => { const d = new Date(ms); d.setDate(d.getDate() + n); return d.getTime(); };
const isoDay = (ms) => {
    const d = new Date(ms);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};
// DST makes some days 23/25h long, so count calendar days rather than dividing by DAY
const daysBetween = (a, b) => Math.round((startOfDay(b) - startOfDay(a)) / DAY);

Alpine.data('laneTimeline', (dataId, detailUrl) => ({
    lanes: [],
    origin: 0,        // local midnight of the first column
    baseDays: 0,
    dayCount: 0,
    dayW: 24,
    nowMs: Date.now(),
    scrollX: 0,
    viewW: 0,
    hover: null,      // {day, x, y}
    drag: null,
    lang: document.documentElement.lang || undefined,

    init() {
        const data = JSON.parse(document.getElementById(dataId).textContent);
        this.lanes = data.lanes.map((lane) => ({
            ...lane,
            events: lane.events.map((e) => ({
                ...e,
                s: new Date(e.start).getTime(),
                e: e.end ? new Date(e.end).getTime() : null,
            })),
        }));
        this.nowMs = new Date(data.now).getTime();
        // a year of room either side of the data (or from the range filter), never more
        const first = startOfDay(new Date(data.range_start).getTime());
        const last = Math.max(new Date(data.range_end).getTime(), this.nowMs);
        const pad = (ms, years) => { const d = new Date(ms); d.setFullYear(d.getFullYear() + years); return d.getTime(); };
        this.origin = data.starts_at_filter ? first : pad(first, -1);
        this.baseDays = daysBetween(this.origin, pad(last, 1)) + 1;

        const vp = this.$refs.viewport;
        this.measure();
        // default zoom: roughly the last five weeks across the screen, or everything if less
        this.dayW = Math.min(MAX_DAY_W, this.viewW / Math.min(this.baseDays, 35));
        this.recount();
        this.$nextTick(() => { vp.scrollLeft = this.x(this.nowMs) - this.viewW * 0.8; this.onScroll(); });

        new ResizeObserver(() => { this.measure(); this.recount(); }).observe(vp);
    },

    // the sticky lane labels sit inside the scroller; the track is what's left of it
    labelW: 0,
    measure() {
        this.labelW = this.$el.querySelector('.nle__corner').offsetWidth;
        this.viewW = this.$refs.viewport.clientWidth - this.labelW;
    },

    // zooming out stops once the whole padded range fits the viewport
    get minDayW() {
        return Math.min(MAX_DAY_W, this.viewW / this.baseDays);
    },

    recount() {
        this.dayW = Math.max(this.dayW, this.minDayW);
        this.dayCount = this.baseDays;
    },

    // position by calendar day + fraction of that day, so columns and events agree across DST
    x(ms) {
        const day = daysBetween(this.origin, ms);
        const dayStart = addDays(this.origin, day);
        const len = addDays(dayStart, 1) - dayStart;
        return (day + (ms - dayStart) / len) * this.dayW;
    },
    dayAt(px) { return Math.floor(px / this.dayW); },
    get width() { return this.dayCount * this.dayW; },

    // Grid lines sit exactly on day boundaries (one element each, only on screen) so they
    // can't drift from the days they mark. Every day while there's room, then Mondays,
    // then the 1st of each month.
    get gridLines() {
        const every = this.dayW >= 6 ? 'day' : this.dayW >= 1.2 ? 'week' : 'month';
        const from = Math.max(0, this.dayAt(this.scrollX) - 1);
        const to = Math.min(this.dayCount, this.dayAt(this.scrollX + this.viewW) + 2);
        const out = [];
        for (let i = from; i < to; i++) {
            const d = new Date(addDays(this.origin, i));
            const month = d.getDate() === 1;
            if (every === 'day' || month || (every === 'week' && d.getDay() === 1)) {
                out.push({i, left: i * this.dayW, month});
            }
        }
        return out;
    },

    // only build labels for what's on screen
    get visibleDays() {
        if (this.dayW < 20) return [];
        const from = Math.max(0, this.dayAt(this.scrollX) - 1);
        const to = Math.min(this.dayCount, this.dayAt(this.scrollX + this.viewW) + 2);
        const wdFmt = new Intl.DateTimeFormat(this.lang, {weekday: 'short'});
        const today = isoDay(this.nowMs);
        const out = [];
        for (let i = from; i < to; i++) {
            const ms = addDays(this.origin, i);
            const d = new Date(ms);
            out.push({
                i, left: i * this.dayW, num: d.getDate(),
                wd: this.dayW >= 56 ? wdFmt.format(d) : '',
                weekend: d.getDay() === 0 || d.getDay() === 6,
                today: isoDay(ms) === today,
            });
        }
        return out;
    },

    // Month labels for what's on screen, as detailed as the zoom allows: full names, short
    // names, then every 2nd/3rd/6th month, then years only. The current label sticks to the
    // left edge but always yields to the next one instead of overlapping it.
    get months() {
        const monthW = this.dayW * 30.44;
        const step = monthW >= 36 ? 1 : [2, 3, 6, 12].find((n) => monthW * n >= 44) || 12;
        const fmt = monthW >= 150
            ? new Intl.DateTimeFormat(this.lang, {month: 'long', year: 'numeric'})
            : monthW >= 80
                ? new Intl.DateTimeFormat(this.lang, {month: 'short', year: 'numeric'})
                : new Intl.DateTimeFormat(this.lang, {month: 'short'});
        const labelOf = (d) => {
            const text = step === 12 || (monthW < 80 && d.getMonth() === 0)
                ? String(d.getFullYear())
                : fmt.format(d).replace('.', '');
            return text[0].toUpperCase() + text.slice(1);
        };

        // labelled months: every `step`-th month, aligned to the calendar (Jan, Apr, Jul...)
        const end = addDays(this.origin, this.dayCount);
        const marks = [];
        let d = new Date(this.origin);
        d = new Date(d.getFullYear(), d.getMonth() - (d.getMonth() % step), 1);
        while (d.getTime() < end) {
            marks.push(d);
            d = new Date(d.getFullYear(), d.getMonth() + step, 1);
        }

        const viewEnd = this.scrollX + this.viewW;
        const out = [];
        marks.forEach((m, i) => {
            const x0 = this.x(m.getTime());
            const x1 = i + 1 < marks.length ? this.x(marks[i + 1].getTime()) : this.width;
            if (x1 <= this.scrollX || x0 >= viewEnd) return;
            const label = labelOf(m);
            const w = label.length * 7 + 14;
            if (x1 - Math.max(x0, this.scrollX, 0) < w) return;  // no room: drop it
            out.push({
                key: m.getTime(),
                left: Math.max(0, Math.min(Math.max(x0, this.scrollX), x1 - w)),
                label,
            });
        });
        return out;
    },

    get todayLeft() { return daysBetween(this.origin, this.nowMs) * this.dayW; },

    // a combo lane's dot is split into one slice per tag colour
    swatch(lane) {
        const c = lane.tags.map((t) => t.color);
        if (!c.length) return 'var(--muted-foreground)';
        if (c.length === 1) return c[0];
        return `conic-gradient(${c.map((col, i) => `${col} ${(i / c.length) * 100}% ${((i + 1) / c.length) * 100}%`).join(', ')})`;
    },

    barStyle(ev) {
        // an all-day moment sits mid-day rather than on the day's left edge
        if (!ev.e) return `left: ${this.x(ev.all_day ? ev.s + DAY / 2 : ev.s)}px`;
        const left = this.x(ev.s);
        return `left: ${left}px; width: ${Math.max(this.x(ev.e) - left, 6)}px`;
    },

    // -------- zoom
    setZoom(next, anchorPx = this.viewW / 2) {
        const vp = this.$refs.viewport;
        const t = (vp.scrollLeft + anchorPx) / this.dayW;     // day under the anchor stays put
        this.dayW = Math.min(MAX_DAY_W, Math.max(this.minDayW, next));
        this.recount();
        this.$nextTick(() => { vp.scrollLeft = t * this.dayW - anchorPx; this.onScroll(); });
    },

    // buttons glide; wheel zoom follows the input directly
    zoomBy(factor) {
        const from = this.dayW;
        const to = Math.min(MAX_DAY_W, Math.max(this.minDayW, from * factor));
        if (matchMedia('(prefers-reduced-motion: reduce)').matches) return this.setZoom(to);
        const t0 = performance.now();
        const step = (now) => {
            const p = Math.min(1, (now - t0) / 220);
            this.setZoom(from + (to - from) * (1 - Math.pow(1 - p, 3)));
            if (p < 1) requestAnimationFrame(step);
        };
        requestAnimationFrame(step);
    },

    fitAll() {
        this.setZoom(this.viewW / this.baseDays);
        this.$nextTick(() => { this.$refs.viewport.scrollLeft = 0; this.onScroll(); });
    },

    goToday() {
        this.$refs.viewport.scrollTo({left: this.x(this.nowMs) - this.viewW * 0.8, behavior: 'smooth'});
    },

    onWheel(e) {
        if (!(e.ctrlKey || e.altKey || e.metaKey)) return;
        e.preventDefault();
        const rect = this.$refs.viewport.getBoundingClientRect();
        this.setZoom(this.dayW * Math.exp(-e.deltaY * 0.0025), Math.max(0, e.clientX - rect.left - this.labelW));
    },

    onScroll() {
        this.scrollX = this.$refs.viewport.scrollLeft;
    },

    // -------- pan by dragging, click to log
    onPointerDown(e) {
        if (e.button !== 0 || e.target.closest('[data-event]')) return;
        this.drag = {x: e.clientX, scroll: this.$refs.viewport.scrollLeft, moved: false, id: e.pointerId};
    },

    onPointerMove(e) {
        if (this.drag) {
            const dx = e.clientX - this.drag.x;
            if (Math.abs(dx) > 4 && !this.drag.moved) {
                this.drag.moved = true;
                this.$refs.viewport.setPointerCapture(this.drag.id);
            }
            if (this.drag.moved) {
                this.$refs.viewport.scrollLeft = this.drag.scroll - dx;
                this.hover = null;
                return;
            }
        }
        // over the sticky labels: no day under the pointer
        if (e.clientX < this.$refs.viewport.getBoundingClientRect().left + this.labelW) {
            this.hover = null;
            return;
        }
        const rect = this.$refs.strip.getBoundingClientRect();
        const laneEl = e.target.closest('[data-lane]');
        this.hover = {
            day: this.dayAt(e.clientX - rect.left),
            lane: laneEl ? Number(laneEl.dataset.lane) : null,  // the row a click would log into
            x: e.clientX, y: e.clientY,
        };
    },

    onPointerUp(e) {
        const drag = this.drag;
        this.drag = null;
        if (!drag || drag.moved || e.target.closest('[data-event]')) return;
        const laneEl = e.target.closest('[data-lane]');
        if (!laneEl || !this.hover) return;
        const lane = this.lanes[Number(laneEl.dataset.lane)];
        window.dispatchEvent(new CustomEvent('open-quick-log', {
            detail: {date: isoDay(addDays(this.origin, this.hover.day)), tags: lane.tags.map((t) => t.slug)},
        }));
    },

    openEvent(id) {
        htmx.ajax('GET', detailUrl.replace('/0/', `/${id}/`), {target: '#generic-offcanvas'});
    },

    // -------- hover card: everything on the hovered day, across all lanes
    get hoverInfo() {
        if (!this.hover) return null;
        const from = addDays(this.origin, this.hover.day);
        const to = addDays(from, 1);
        const groups = this.lanes
            .map((lane) => ({
                lane,
                items: lane.events.filter((ev) => (ev.e ? ev.s < to && ev.e >= from : ev.s >= from && ev.s < to)),
            }))
            .filter((g) => g.items.length);
        const label = new Intl.DateTimeFormat(this.lang, {weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'})
            .format(new Date(from));
        return {label, groups, from};
    },

    // an object, not a string: a string :style would wipe x-show's display:none
    get hoverCardStyle() {
        if (!this.hover) return {};
        const w = 288;
        return {
            left: `${Math.min(this.hover.x + 16, window.innerWidth - w - 12)}px`,
            top: `${Math.min(this.hover.y + 18, window.innerHeight - 240)}px`,
            width: `${w}px`,
        };
    },

    timeLabel(ev, dayStart) {
        if (ev.e && ev.s < dayStart) return '…';
        if (ev.all_day) return suggestConfig().presets?.allDay || '';
        return new Intl.DateTimeFormat(this.lang, {hour: '2-digit', minute: '2-digit'}).format(new Date(ev.s));
    },
}));
