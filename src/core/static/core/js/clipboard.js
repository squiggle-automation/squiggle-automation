// "Copy to clipboard" buttons: data-clipboard-target points to the id of the element whose
// textContent should be copied. Translated labels come from data attributes (data-label-copy/
// data-label-copied/data-label-error) set by the template, not hardcoded here.
document.addEventListener("click", function (event) {
    var button = event.target.closest(".copy-json-btn");
    if (!button) {
        return;
    }

    var icon = button.querySelector(".copy-json-btn-icon");
    var label = button.querySelector(".copy-json-btn-label");
    var content = document.getElementById(button.dataset.clipboardTarget).textContent;

    var reset = function () {
        icon.className = "bi bi-clipboard copy-json-btn-icon";
        label.textContent = button.dataset.labelCopy;
    };

    navigator.clipboard
        .writeText(content)
        .then(function () {
            icon.className = "bi bi-check-lg copy-json-btn-icon";
            label.textContent = button.dataset.labelCopied;
            setTimeout(reset, 1500);
        })
        .catch(function () {
            icon.className = "bi bi-x-lg copy-json-btn-icon";
            label.textContent = button.dataset.labelError;
            setTimeout(reset, 1500);
        });
});
