/*
 * Minimal SurveyCTO field plug-in script (text fields).
 *
 * Contract:
 * - The host renders template.html through Mustache against a global
 *   `fieldProperties` object, then loads style.css and this script.
 * - This script must define `clearAnswer()` and should call `setAnswer(value)`
 *   whenever the user changes the answer.
 * - On load, restore UI state from `fieldProperties.CURRENT_ANSWER` so the
 *   field reflects a previously saved value after save/resume.
 */

(function () {
  var input = document.getElementById('plugin-input');

  if (!input) {
    // Defensive: template.html is the source of truth. If the input went
    // missing, log and bail rather than throwing inside the host.
    console.warn('[field-plugin] template.html is missing #plugin-input');
    return;
  }

  // Honor read-only state. fieldProperties.READONLY is also reflected on the
  // document via the `is-read-only` class, but we still want to disable the
  // input so it can't receive keystrokes.
  if (typeof fieldProperties !== 'undefined' && fieldProperties.READONLY) {
    input.readOnly = true;
  }

  // Push every change to the host. Use 'input' so we catch every keystroke,
  // paste, and IME composition update.
  input.addEventListener('input', function () {
    if (typeof setAnswer === 'function') {
      setAnswer(input.value);
    }
  });
})();

// Required: clear the field on demand. The host calls this when the user
// triggers "clear answer" or when other form logic resets the field.
function clearAnswer() {
  var input = document.getElementById('plugin-input');
  if (input) {
    input.value = '';
  }
}

// Optional: take focus when the host navigates to this field. Implementing
// this gives a nicer experience than relying on the browser's default.
function setFocus() {
  var input = document.getElementById('plugin-input');
  if (input && !input.readOnly) {
    input.focus();
  }
}
