// Drives the jedison-generated form for the entity "data" field, with a fallback to editing
// the raw JSON directly.
document.querySelectorAll("[data-jedison-widget]").forEach(function (root) {
    var hiddenInput = root.querySelector("[data-jedison-value]");
    var container = root.querySelector("[data-jedison-container]");
    var rawBlock = root.querySelector("[data-jedison-raw]");
    var textarea = root.querySelector("[data-jedison-textarea]");
    var rawError = root.querySelector("[data-jedison-raw-error]");
    var toggleButton = root.querySelector("[data-jedison-toggle]");
    var schema = JSON.parse(document.getElementById(root.dataset.jedisonSchema).textContent);

    var mode = "form";
    var instance = null;

    var parseInitialValue = function () {
        if (!hiddenInput.value) {
            return undefined;
        }
        try {
            var parsed = JSON.parse(hiddenInput.value);
            return parsed === null ? undefined : parsed;
        } catch (error) {
            return undefined;
        }
    };

    var initForm = function (value) {
        if (instance) {
            instance.destroy();
        }
        var options = {
            container: container,
            theme: new Jedison.ThemeBootstrap5(),
            schema: schema,
            objectAdd: false,
        };
        if (value !== undefined) {
            options.data = value;
        }
        instance = new Jedison.Create(options);
    };

    var showRawView = function () {
        container.hidden = true;
        rawBlock.hidden = false;
        toggleButton.textContent = toggleButton.dataset.jedisonLabelFormView;
        mode = "raw";
    };

    var showFormView = function () {
        rawBlock.hidden = true;
        rawError.hidden = true;
        container.hidden = false;
        toggleButton.textContent = toggleButton.dataset.jedisonLabelRawView;
        mode = "form";
    };

    var switchToRaw = function () {
        textarea.value = instance ? JSON.stringify(instance.getValue(), null, 2) : hiddenInput.value;
        if (instance) {
            instance.destroy();
            instance = null;
        }
        showRawView();
    };

    var switchToForm = function () {
        var text = textarea.value.trim();
        var parsed;
        try {
            parsed = text ? JSON.parse(text) : undefined;
        } catch (error) {
            rawError.textContent = root.dataset.jedisonErrorInvalidJson;
            rawError.hidden = false;
            return;
        }
        initForm(parsed);
        showFormView();
    };

    // initial render: if the hidden input holds non-empty text that fails to parse as JSON
    // (a redisplay after a literal JSON syntax error), start in raw mode showing that text
    // untouched instead of silently discarding it
    var initialValue = parseInitialValue();
    if (hiddenInput.value && hiddenInput.value !== "null" && initialValue === undefined) {
        textarea.value = hiddenInput.value;
        showRawView();
    } else {
        initForm(initialValue);
    }

    toggleButton.addEventListener("click", function () {
        if (mode === "form") {
            switchToRaw();
        } else {
            switchToForm();
        }
    });

    root.jedisonWidget = {
        readValueForSubmit: function () {
            if (mode === "form") {
                return { ok: true, value: JSON.stringify(instance.getValue()) };
            }
            var text = textarea.value.trim();
            if (!text) {
                return { ok: true, value: "" };
            }
            try {
                JSON.parse(text);
                return { ok: true, value: text };
            } catch (error) {
                return { ok: false };
            }
        },
        showRawError: function () {
            if (mode !== "raw") {
                switchToRaw();
            }
            rawError.textContent = root.dataset.jedisonErrorInvalidJson;
            rawError.hidden = false;
        },
        hiddenInput: hiddenInput,
    };
});

document.addEventListener("submit", function (event) {
    var root = event.target.querySelector && event.target.querySelector("[data-jedison-widget]");
    if (!root || !root.jedisonWidget) {
        return;
    }

    var result = root.jedisonWidget.readValueForSubmit();
    if (!result.ok) {
        event.preventDefault();
        root.jedisonWidget.showRawError();
        return;
    }
    root.jedisonWidget.hiddenInput.value = result.value;
});
