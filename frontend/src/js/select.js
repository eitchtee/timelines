import TomSelect from "tom-select";
import * as Popper from "@popperjs/core";
import '../styles/_tom-select.scss'


window.TomSelect = function createDynamicTomSelect(element) {
    const schedulePopperUpdate = function (instance) {
        // Wait for TomSelect DOM updates before recalculating dropdown position.
        requestAnimationFrame(() => {
            if (instance.popper) {
                instance.popper.update();
            }
        });
    };

    // Basic configuration
    const config = {
        plugins: {},
        maxOptions: null,

        // Extract 'create' option from data attribute
        create: element.dataset.create === 'true',
        copyClassesToDropdown: true,
        loadingClass: "ts-loading",
        allowEmptyOption: element.dataset.allowEmptyOption === 'true',
        render: {
            no_results: function (data) {
                // when typing can create the option, "Add …" is already the answer
                if (element.dataset.create === 'true' && data.input) return null;
                return `<div class="no-results">${element.dataset.txtNoResults || 'No results...'}</div>`;
            },
            option_create: function (data, escape) {
                return `<div class="create">${element.dataset.txtCreate || 'Add'} <strong>${escape(data.input)}</strong>&hellip;</div>`;
            },
        },

        onInitialize: function () {
            this.popper = Popper.createPopper(this.control, this.dropdown, {
                placement: "bottom-start",
                modifiers: [
                    {
                        name: "offset",
                        options: {
                            offset: [0, 4],
                        },
                    },
                    {
                        name: "sameWidth",
                        enabled: true,
                        fn: ({ state }) => {
                            state.styles.popper.width = `${state.rects.reference.width}px`;
                        },
                        phase: "beforeWrite",
                        requires: ["computeStyles"],
                    },
                    {
                        name: 'flip',
                        options: {
                            fallbackPlacements: ['top-start'],
                        },
                    },
                ]

            });
        },
        onDropdownOpen: function () {
            schedulePopperUpdate(this);
        },
        onItemAdd: function () {
            if (this.settings.mode === 'multi') {
                this.setTextboxValue();
                this.refreshOptions(false);
            }
            schedulePopperUpdate(this);
        },
        onItemRemove: function () {
            schedulePopperUpdate(this);
        },
        onClear: function () {
            schedulePopperUpdate(this);
        },
    };

    if (element.dataset.checkboxes === 'true') {
        config.plugins.checkbox_options = {
            'checkedClassNames': ['ts-checked', "checkbox", "checkbox-xs"],
            'uncheckedClassNames': ['ts-checked', "checkbox", "checkbox-xs"],
        };
    }

    if (element.dataset.clearButton === 'true') {
        config.plugins.clear_button = {
            'title': element.dataset.txtClear || 'Clear',
        };
    }

    if (element.dataset.removeButton === 'true') {
        config.plugins.remove_button = {
            'title': element.dataset.txtRemove || 'Remove',
        };
    }

    if (element.dataset.load) {
        config.load = function (query, callback) {
            let url = element.dataset.load + '?q=' + encodeURIComponent(query);
            fetch(url)
                .then(response => response.json())
                .then(json => {
                    // data-load-key: endpoints that wrap the list, e.g. {"tags": [...]}
                    callback(element.dataset.loadKey ? json[element.dataset.loadKey] : json);
                }).catch(() => {
                    callback();
                });
        };
    }

    // map an endpoint's own field names instead of value/text
    if (element.dataset.valueField) config.valueField = element.dataset.valueField;
    if (element.dataset.labelField) {
        config.labelField = element.dataset.labelField;
        config.searchField = [element.dataset.labelField];
    }
    if (element.dataset.preload) config.preload = element.dataset.preload;  // e.g. "focus"
    // render inside e.g. "body" when an overflow container would clip the dropdown
    if (element.dataset.dropdownParent) config.dropdownParent = element.dataset.dropdownParent;

    // data-color-field: a coloured dot before each option and selected item (tags)
    if (element.dataset.colorField) {
        const colorKey = element.dataset.colorField;
        const label = config.labelField || 'text';
        const dot = (data, escape) => data[colorKey]
            ? `<span class="ts-dot" style="background:${escape(data[colorKey])}"></span>` : '';
        config.render.option = (data, escape) => `<div>${dot(data, escape)}${escape(data[label])}</div>`;
        config.render.item = (data, escape) => `<div>${dot(data, escape)}${escape(data[label])}</div>`;
    }

    // Create and return the TomSelect instance
    return new TomSelect(element, config);
};
